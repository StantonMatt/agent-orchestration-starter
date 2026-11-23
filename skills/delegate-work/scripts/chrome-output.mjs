// Output boundary only: browser handles and navigation URLs stay untouched.
const MASK = '<redacted>';
const SECRET = /^(?:token|code|state|codechallenge|accesstoken|idtoken|refreshtoken|password|passwd|secret|apikey|authorization)$/i;
const secretKey = key => SECRET.test(key.replace(/[_-]/g, ''));
const maskedValue = value => /^["']/.test(value) ? `${value[0]}${MASK}${value[0]}` : MASK;

function redactText(text) {
  text = text
    .replace(/\bBearer\s+(?:<redacted>|[a-z\d._~+\/-]+=*)/gi, `Bearer ${MASK}`)
    // Header credentials can contain spaces, commas and quoted parameters.
    .replace(/(\bauthorization["']?\s*[:=]\s*)("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\r\n]+)/gi,
      (_, prefix, value) => prefix + maskedValue(value))
    .replace(/(\b(token|code|state|code[_-]?challenge|access[_-]?token|id[_-]?token|refresh[_-]?token|password|passwd|secret|api[_-]?key)(["']?)\s*([:=])\s*)("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|<redacted>|[^\s,;&#}\])<>"'](?:[^\s,;&#}\])<>]*[^\s,;&#}\])<>"'])?)/gi,
      (match, prefix, key, keyQuote, separator, value, offset, whole) => {
        // `key: value` in a snapshot name ("ZIP code: optional": …) must not eat the
        // name's closing quote, so an unquoted colon value stops at the first quote;
        // `key=value` keeps any inner quotes as part of the value.
        let rest = '';
        const cut = separator === ':' && !/^["']/.test(value) ? value.search(/["']/) : -1;
        if (cut >= 0) {
          rest = value.slice(cut);
          value = value.slice(0, cut);
          match = match.slice(0, match.length - rest.length);
        }
        const plain = /^["']/.test(value) ? value.slice(1, -1) : value;
        // Ambiguous colon labels (e.g. "ZIP code: optional") are readable text;
        // a quoted key ("code": …) or quoted code value is a structured field.
        const structured = keyQuote !== '' && whole[offset - 1] === keyQuote;
        const ambiguous = /^(?:token|code|state)$/i.test(key);
        const tokenLike = !/\s/.test(plain) && (plain.length >= 16 || (plain.length >= 6 && /[^a-z]/i.test(plain)));
        return (separator === '=' || structured || (key.toLowerCase() === 'code' && /^["']/.test(value)) || !ambiguous || tokenLike ? prefix + maskedValue(value) : match) + rest;
      });
  const urls = [];
  // Absolute and root-relative URLs, including URLs embedded in snapshots.
  text = text.replace(/(?:\b[a-z][a-z\d+.-]*:|(?<![a-z\d_+\/-])\/)(?:<redacted>|[^\s<>"`])+/gi, url => {
    url = url.replace(/(\/\/)[^/?#@]*@/, `$1${MASK}@`);
    const hash = url.indexOf('#');
    const fragment = hash < 0 ? '' : `#${MASK}`;
    if (hash >= 0) url = url.slice(0, hash);
    const query = url.indexOf('?');
    const safe = query < 0 ? url + fragment : url.slice(0, query + 1) + url.slice(query + 1).split('&').map(part => {
      const equal = part.indexOf('=');
      return equal < 0 ? part : part.slice(0, equal + 1) + MASK;
    }).join('&') + fragment;
    // Keep host/path and parameter names readable even when they look opaque.
    return `\0URL${urls.push(safe) - 1}\0`;
  });
  return text
    .replace(/\b[a-z\d_-]{8,}\.[a-z\d_-]{8,}\.[a-z\d_-]{8,}\b/gi, MASK)
    .replace(/(?<![a-z\d_+/-])[a-z\d_+/-]{32,}={0,2}(?![a-z\d_+/-])/gi, MASK)
    .replace(/\0URL(\d+)\0/g, (_, index) => urls[Number(index)] ?? MASK);
}

// Return plain data, never custom inspectors/toJSON or live browser objects.
export function redact(value, seen = new WeakSet()) {
  if (typeof value === 'string') return redactText(value);
  if (value === null || ['number', 'boolean', 'undefined'].includes(typeof value)) return value;
  if (typeof value !== 'object') return '[unsupported value]';
  if (seen.has(value)) return '[circular]';
  seen.add(value);
  try {
    if (Array.isArray(value)) return value.map(item => redact(item, seen));
    if (value instanceof Error) {
      return { name: redactText(value.name), message: redactText(value.message) };
    }
    return Object.fromEntries(Object.entries(Object.getOwnPropertyDescriptors(value)).map(([key, field]) => [
      redactText(key), secretKey(key) ? MASK : 'value' in field ? redact(field.value, seen) : '[accessor omitted]',
    ]));
  } finally { seen.delete(value); }
}

// The runtime is frozen. Shadow its REPL binding with this clone; never mutate it.
export function installChromeRedaction(runtime) {
  const say = (...values) => runtime.write(...values.map(value => redact(value)));
  try {
    const fields = Object.getOwnPropertyDescriptors(runtime);
    for (const field of Object.values(fields)) {
      if (typeof field.value === 'function') field.value = field.value.bind(runtime);
      if (field.get) field.get = field.get.bind(runtime);
      if (field.set) field.set = field.set.bind(runtime);
    }
    fields.write = { value: say, enumerable: true };
    return { nodeRepl: Object.defineProperties({}, fields), say, mode: 'shadow' };
  } catch {
    // Some runtimes may refuse reflection. Explicit say() still redacts output.
    return { nodeRepl: runtime, say, mode: 'say' };
  }
}
