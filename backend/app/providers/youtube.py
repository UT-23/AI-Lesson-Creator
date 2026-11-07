"""YouTube provider interface + YouTube Data API v3 implementation.

Quota: search.list = 100 units, videos.list = 1 unit (10,000 units/day free).

Relevance check order (configurable, default per the spec):
  1. "video"      — Gemini watches the public YouTube URL (file_data part)
  2. "transcript" — youtube-transcript-api transcript, judged by the LLM
  3. "metadata"   — title + description only; conservative, and never yields key points
The first method that succeeds decides. The method used is recorded on the verdict.
"""

import html
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Literal

import httpx
from pydantic import BaseModel

from app.providers.errors import ErrorKind, ProviderError, RetryPolicy, request_json
from app.providers.llm import LLMOutputError, LLMProvider, generate_structured
from app.schemas import VideoRelevanceJudgement

log = logging.getLogger(__name__)


class VideoCandidate(BaseModel):
    video_id: str
    url: str
    title: str
    channel_title: str = ""
    description: str = ""
    duration_seconds: int | None = None  # filled in by get_details (videos.list)
    view_count: int | None = None
    published_at: str | None = None
    audio_language: str | None = None  # BCP-47 code from videos.list, e.g. "en", "en-US", "hi"


class RelevanceVerdict(BaseModel):
    relevant: bool
    reason: str
    outcomes_matched: list[str] = []
    key_points: list[str] = []  # what the video itself says (empty for metadata-only checks)
    method: Literal["gemini_video", "transcript", "metadata", "fake"]
    spoken_language: str | None = None  # as judged by the model
    suggested_segment: str | None = None  # "mm:ss-mm:ss"
    transcript_excerpt: str | None = None


class YouTubeProvider(ABC):
    name: str = "youtube"

    @abstractmethod
    def search(self, query: str, max_results: int = 8) -> list[VideoCandidate]:
        """search.list — expensive (100 quota units)."""

    @abstractmethod
    def get_details(self, video_ids: list[str]) -> list[VideoCandidate]:
        """videos.list — durations, channel, stats (1 unit)."""

    @abstractmethod
    def check_relevance(self, video: VideoCandidate, lesson_title: str, outcomes: list[str]) -> RelevanceVerdict:
        """Does this video actually teach the outcomes?"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

YT_API = "https://www.googleapis.com/youtube/v3"
_ISO_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_iso_duration(value: str | None) -> int | None:
    """'PT12M34S' → 754 seconds. None if missing/unparseable."""
    if not value:
        return None
    match = _ISO_DURATION.match(value)
    if not match:
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def mmss(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def classify_youtube_error(resp: httpx.Response) -> tuple[ErrorKind, str] | None:
    try:
        reason = resp.json()["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError, TypeError):
        reason = ""
    if reason in ("quotaExceeded", "dailyLimitExceeded"):
        return ErrorKind.quota_exhausted, "YouTube Data API daily quota is used up (resets at midnight Pacific time)."
    if reason in ("keyInvalid", "keyExpired") or resp.status_code == 401:
        return ErrorKind.auth, "YouTube rejected the API key. Check YOUTUBE_API_KEY."
    if reason == "accessNotConfigured":
        return ErrorKind.auth, "YouTube Data API v3 is not enabled for this API key's Google Cloud project."
    if resp.status_code == 403:
        return ErrorKind.auth, f"YouTube refused the request (HTTP 403, reason '{reason or 'unknown'}')."
    return None


TranscriptFetcher = Callable[[str], list[tuple[float, str]]]  # video_id → [(start_seconds, text)]


def fetch_transcript(video_id: str) -> list[tuple[float, str]]:
    """English transcript via youtube-transcript-api (works locally; often blocked from cloud IPs)."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api import YouTubeTranscriptApiException

    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en", "en-US", "en-GB"])
    except YouTubeTranscriptApiException as exc:
        raise ProviderError("youtube-transcript", ErrorKind.unavailable,
                            f"No transcript for {video_id}: {type(exc).__name__}") from exc
    return [(s.start, s.text) for s in fetched.snippets]


def transcript_text(lines: list[tuple[float, str]], max_chars: int = 20000) -> str:
    """Transcript with a [mm:ss] marker roughly every 30 seconds (lets the model suggest segments)."""
    out: list[str] = []
    next_mark = 0.0
    for start, text in lines:
        if start >= next_mark:
            out.append(f"\n[{mmss(start)}]")
            next_mark = start + 30
        out.append(text.replace("\n", " "))
    return " ".join(out).strip()[:max_chars]


RELEVANCE_SYSTEM = "You vet supplementary videos for a short lesson. Be strict and never invent what a video says."
# Bump when the relevance prompt changes, so cached verdicts from the old prompt are not reused.
RELEVANCE_PROMPT_VERSION = 3


def _relevance_prompt(video: VideoCandidate, title: str, outcomes: list[str], evidence: str) -> str:
    outcome_lines = "\n".join(f"- {o}" for o in outcomes)
    minutes = f"{video.duration_seconds / 60:.1f} min" if video.duration_seconds else "unknown length"
    return f"""Decide whether this YouTube video is a good supplementary resource for the lesson.

LESSON: {title}
OUTCOMES:
{outcome_lines}

VIDEO: "{video.title}" by {video.channel_title or 'unknown channel'} ({minutes})

{evidence}

Rules:
- relevant = true only if a substantial part of the video directly teaches at least one outcome at an
  introductory level. Off-topic, mostly promotional, or far too advanced videos are not relevant.
- The lesson is in English: a video whose narration is mainly in another language (even with an
  English title) is NOT relevant. Say which language it is in the reason.
- outcomes_matched: copy the exact outcome texts the video teaches.
- key_points: 3-6 factual statements the video itself makes. Only what the video says.
- suggested_segment: "mm:ss-mm:ss" for the most useful part if the whole video is not needed, else null.
- reason: one or two sentences."""


class UnconfiguredYouTube(YouTubeProvider):
    """Used when YOUTUBE_API_KEY is missing: the (optional) YouTube step fails with a clear warning."""

    name = "youtube"

    def _fail(self) -> ProviderError:
        return ProviderError("youtube", ErrorKind.not_configured,
                             "YOUTUBE_API_KEY is not set, so no videos were researched. Add it to .env and retry this step.")

    def search(self, query: str, max_results: int = 8) -> list[VideoCandidate]:
        raise self._fail()

    def get_details(self, video_ids: list[str]) -> list[VideoCandidate]:
        raise self._fail()

    def check_relevance(self, video: VideoCandidate, lesson_title: str, outcomes: list[str]) -> RelevanceVerdict:
        raise self._fail()


# ---------------------------------------------------------------------------
# YouTube Data API v3
# ---------------------------------------------------------------------------


class YouTubeDataProvider(YouTubeProvider):
    name = "youtube"

    def __init__(
        self,
        api_key: str,
        *,
        llm: LLMProvider | None,
        relevance_order: list[str] | None = None,
        timeout_s: float = 30.0,
        retry: RetryPolicy = RetryPolicy(),
        client: httpx.Client | None = None,
        transcript_fetcher: TranscriptFetcher = fetch_transcript,
    ) -> None:
        if not api_key:
            raise ProviderError("youtube", ErrorKind.not_configured, "YOUTUBE_API_KEY is not set.")
        self._key = api_key
        self._llm = llm
        self._order = relevance_order or ["video", "transcript", "metadata"]
        self._client = client or httpx.Client(timeout=timeout_s)
        self._retry = retry
        self._fetch_transcript = transcript_fetcher

    def _get(self, path: str, params: dict) -> dict:
        return request_json(self._client, "GET", f"{YT_API}{path}", provider="youtube", retry=self._retry,
                            classify=classify_youtube_error, params={**params, "key": self._key})

    def search(self, query: str, max_results: int = 8) -> list[VideoCandidate]:
        data = self._get("/search", {
            "part": "snippet", "type": "video", "q": query, "maxResults": min(max_results, 50),
            "relevanceLanguage": "en", "safeSearch": "strict", "videoEmbeddable": "true",
        })
        videos = []
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            if not vid:
                continue
            videos.append(VideoCandidate(
                video_id=vid,
                url=f"https://www.youtube.com/watch?v={vid}",
                title=html.unescape(snippet.get("title", "")),
                channel_title=html.unescape(snippet.get("channelTitle", "")),
                description=html.unescape(snippet.get("description", "")),
                published_at=snippet.get("publishedAt"),
            ))
        return videos

    def get_details(self, video_ids: list[str]) -> list[VideoCandidate]:
        if not video_ids:
            return []
        data = self._get("/videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(video_ids[:50])})
        videos = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            views = item.get("statistics", {}).get("viewCount")
            videos.append(VideoCandidate(
                video_id=item["id"],
                url=f"https://www.youtube.com/watch?v={item['id']}",
                title=html.unescape(snippet.get("title", "")),
                channel_title=html.unescape(snippet.get("channelTitle", "")),
                description=snippet.get("description", ""),  # full description (search.list truncates it)
                duration_seconds=parse_iso_duration(item.get("contentDetails", {}).get("duration")),
                view_count=int(views) if views is not None else None,
                published_at=snippet.get("publishedAt"),
                # Uploader-declared language; often missing, but reliable when present.
                audio_language=snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage"),
            ))
        return videos

    def check_relevance(self, video: VideoCandidate, lesson_title: str, outcomes: list[str]) -> RelevanceVerdict:
        if self._llm is None:
            raise ProviderError("youtube", ErrorKind.not_configured, "No LLM configured for the relevance check.")
        failures: list[str] = []
        for method in self._order:
            try:
                if method == "video" and self._llm.supports_video:
                    return self._judge(video, lesson_title, outcomes, "gemini_video",
                                       "Watch the attached video before answering.", video_url=video.url)
                if method == "transcript":
                    text = transcript_text(self._fetch_transcript(video.video_id))
                    verdict = self._judge(video, lesson_title, outcomes, "transcript",
                                          f"TRANSCRIPT (may be auto-generated):\n{text}")
                    return verdict.model_copy(update={"transcript_excerpt": text[:6000]})
                if method == "metadata":
                    verdict = self._judge(video, lesson_title, outcomes, "metadata",
                                          "You cannot watch this video. Judge ONLY from the title and description, and be "
                                          "conservative.\nDESCRIPTION:\n" + (video.description[:3000] or "(none)"))
                    return verdict.model_copy(update={"key_points": []})  # nothing was actually verified
            except (ProviderError, LLMOutputError) as exc:
                log.warning("relevance check via %s failed for %s: %s", method, video.video_id, exc)
                failures.append(f"{method}: {exc}")
        raise ProviderError("youtube", ErrorKind.unavailable,
                            f"Could not verify relevance of {video.video_id} ({'; '.join(failures) or 'no method available'})")

    def _judge(self, video: VideoCandidate, lesson_title: str, outcomes: list[str], method: str, evidence: str,
               video_url: str | None = None) -> RelevanceVerdict:
        judgement = generate_structured(
            self._llm,  # type: ignore[arg-type]
            _relevance_prompt(video, lesson_title, outcomes, evidence),
            VideoRelevanceJudgement,
            system=RELEVANCE_SYSTEM,
            max_repairs=1,
            video_url=video_url,
        )
        verdict = RelevanceVerdict(method=method, **judgement.model_dump())  # type: ignore[arg-type]
        language = judgement.spoken_language.strip().lower()
        if verdict.relevant and method != "metadata" and language and not language.startswith("en"):
            # Enforced in code: the prompt rule alone was not reliable.
            verdict = verdict.model_copy(update={
                "relevant": False, "reason": f"Narration is in '{language}', not English. {verdict.reason}"})
        return verdict
