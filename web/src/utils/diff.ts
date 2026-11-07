export interface DiffToken {
  type: 'equal' | 'removed' | 'added';
  text: string;
}

export interface DiffLinePair {
  leftLineNo: number | null;
  rightLineNo: number | null;
  leftText: string | null;
  rightText: string | null;
  status: 'equal' | 'modified' | 'removed' | 'added';
  leftTokens?: DiffToken[];
  rightTokens?: DiffToken[];
}

/**
 * Word-level LCS diff between two strings so modified lines highlight exact changed words.
 */
export function computeWordDiff(before: string, after: string): {
  leftTokens: DiffToken[];
  rightTokens: DiffToken[];
} {
  const leftWords = before.split(/(\s+)/);
  const rightWords = after.split(/(\s+)/);

  const m = leftWords.length;
  const n = rightWords.length;

  // Guard against overly huge paragraphs in word-level DP
  if (m * n > 250000) {
    return {
      leftTokens: [{ type: 'removed', text: before }],
      rightTokens: [{ type: 'added', text: after }],
    };
  }

  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (leftWords[i] === rightWords[j]) {
        dp[i][j] = 1 + dp[i + 1][j + 1];
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  const leftTokens: DiffToken[] = [];
  const rightTokens: DiffToken[] = [];

  const pushToken = (arr: DiffToken[], type: DiffToken['type'], text: string) => {
    if (!text) return;
    const prev = arr[arr.length - 1];
    if (prev && prev.type === type) {
      prev.text += text;
    } else {
      arr.push({ type, text });
    }
  };

  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (leftWords[i] === rightWords[j]) {
      pushToken(leftTokens, 'equal', leftWords[i]);
      pushToken(rightTokens, 'equal', rightWords[j]);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      pushToken(leftTokens, 'removed', leftWords[i]);
      i++;
    } else {
      pushToken(rightTokens, 'added', rightWords[j]);
      j++;
    }
  }
  while (i < m) {
    pushToken(leftTokens, 'removed', leftWords[i]);
    i++;
  }
  while (j < n) {
    pushToken(rightTokens, 'added', rightWords[j]);
    j++;
  }

  return { leftTokens, rightTokens };
}

/**
 * Computes side-by-side line pairs with word-level highlighting on modified lines.
 */
export function computeSideBySideDiff(before: string, after: string): DiffLinePair[] {
  const leftLines = before.split('\n');
  const rightLines = after.split('\n');
  const m = leftLines.length;
  const n = rightLines.length;

  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (leftLines[i] === rightLines[j]) {
        dp[i][j] = 1 + dp[i + 1][j + 1];
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  type RawOp = { op: 'equal' | 'remove' | 'add'; leftIdx?: number; rightIdx?: number; text: string };
  const ops: RawOp[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (leftLines[i] === rightLines[j]) {
      ops.push({ op: 'equal', leftIdx: i, rightIdx: j, text: leftLines[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ op: 'remove', leftIdx: i, text: leftLines[i] });
      i++;
    } else {
      ops.push({ op: 'add', rightIdx: j, text: rightLines[j] });
      j++;
    }
  }
  while (i < m) {
    ops.push({ op: 'remove', leftIdx: i, text: leftLines[i] });
    i++;
  }
  while (j < n) {
    ops.push({ op: 'add', rightIdx: j, text: rightLines[j] });
    j++;
  }

  // Pair adjacent remove+add blocks into side-by-side rows
  const pairs: DiffLinePair[] = [];
  let k = 0;
  while (k < ops.length) {
    if (ops[k].op === 'equal') {
      pairs.push({
        leftLineNo: (ops[k].leftIdx ?? 0) + 1,
        rightLineNo: (ops[k].rightIdx ?? 0) + 1,
        leftText: ops[k].text,
        rightText: ops[k].text,
        status: 'equal',
      });
      k++;
      continue;
    }

    const removed: RawOp[] = [];
    const added: RawOp[] = [];
    while (k < ops.length && ops[k].op !== 'equal') {
      if (ops[k].op === 'remove') removed.push(ops[k]);
      else added.push(ops[k]);
      k++;
    }

    const maxLen = Math.max(removed.length, added.length);
    for (let idx = 0; idx < maxLen; idx++) {
      const r = removed[idx];
      const a = added[idx];
      if (r && a) {
        const { leftTokens, rightTokens } = computeWordDiff(r.text, a.text);
        pairs.push({
          leftLineNo: (r.leftIdx ?? 0) + 1,
          rightLineNo: (a.rightIdx ?? 0) + 1,
          leftText: r.text,
          rightText: a.text,
          status: 'modified',
          leftTokens,
          rightTokens,
        });
      } else if (r) {
        pairs.push({
          leftLineNo: (r.leftIdx ?? 0) + 1,
          rightLineNo: null,
          leftText: r.text,
          rightText: null,
          status: 'removed',
          leftTokens: [{ type: 'removed', text: r.text }],
        });
      } else if (a) {
        pairs.push({
          leftLineNo: null,
          rightLineNo: (a.rightIdx ?? 0) + 1,
          leftText: null,
          rightText: a.text,
          status: 'added',
          rightTokens: [{ type: 'added', text: a.text }],
        });
      }
    }
  }

  return pairs;
}
