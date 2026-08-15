function parseRecord(record) {
  let event = 'message';
  const dataLines = [];
  for (const line of record.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  let data = dataLines.join('\n');
  try {
    data = JSON.parse(data);
  } catch {
    // Keep non-JSON data as text for a standards-compatible parser.
  }
  return { event, data };
}

export async function* parseSse(chunks) {
  let pending = '';
  for await (const chunk of chunks) {
    pending += typeof chunk === 'string' ? chunk : new TextDecoder().decode(chunk);
    let boundary;
    while ((boundary = pending.search(/\r?\n\r?\n/)) !== -1) {
      const record = pending.slice(0, boundary);
      pending = pending.slice(boundary).replace(/^\r?\n\r?\n/, '');
      const parsed = parseRecord(record);
      if (parsed) yield parsed;
    }
  }
  const parsed = parseRecord(pending.trim());
  if (parsed) yield parsed;
}
