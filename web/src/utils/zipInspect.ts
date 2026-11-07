/**
 * Reads the Central Directory of a ZIP archive buffer and returns the exact list of entry filenames.
 * Allows inspecting the exact files included by GET /lessons/{id}/export (including whether
 * lesson.pdf / lesson.docx were generated) even when X-Export-Files is not exposed by CORS.
 */
export function parseZipFileNames(buffer: ArrayBuffer): string[] {
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  const names: string[] = [];
  const decoder = new TextDecoder('utf-8');

  // Scan local file headers (0x04034b50) or central directory headers (0x02014b50)
  // Searching from the end for End of Central Directory (0x06054b50)
  let eocdOffset = -1;
  const minOffset = Math.max(0, bytes.length - 65557);
  for (let i = bytes.length - 22; i >= minOffset; i--) {
    if (view.getUint32(i, true) === 0x06054b50) {
      eocdOffset = i;
      break;
    }
  }

  if (eocdOffset === -1) {
    return names;
  }

  const totalEntries = view.getUint16(eocdOffset + 10, true);
  let cdOffset = view.getUint32(eocdOffset + 16, true);

  for (let e = 0; e < totalEntries && cdOffset + 46 <= bytes.length; e++) {
    const sig = view.getUint32(cdOffset, true);
    if (sig !== 0x02014b50) break;
    const nameLen = view.getUint16(cdOffset + 28, true);
    const extraLen = view.getUint16(cdOffset + 30, true);
    const commentLen = view.getUint16(cdOffset + 32, true);
    const nameBytes = bytes.subarray(cdOffset + 46, cdOffset + 46 + nameLen);
    names.push(decoder.decode(nameBytes));
    cdOffset += 46 + nameLen + extraLen + commentLen;
  }

  return names;
}
