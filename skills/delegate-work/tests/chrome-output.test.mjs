import assert from 'node:assert/strict';
import test from 'node:test';
import { inspect } from 'node:util';
import { redact, installChromeRedaction } from '../scripts/chrome-output.mjs';

test('masks all structured codes without helper-specific exceptions', () => {
  for (const code of ['123456', 'aBc123', 'abcdef', 'unknown_code', 123456]) {
    assert.deepEqual(redact({ code }), { code: '<redacted>' });
    assert.equal(redact(JSON.stringify({ code })), typeof code === 'number'
      ? '{"code":<redacted>}' : '{"code":"<redacted>"}');
    assert.equal(redact(`code=${code}`), 'code=<redacted>');
  }
  assert.deepEqual(redact({ get code() { throw new Error('must not run'); } }),
    { code: '<redacted>' });
  const error = Object.assign(new Error('safe'), { code: '123456', password: 'synthetic-password' });
  assert.deepEqual(redact(error), { name: 'Error', message: 'safe' });
});
// Synthetic page text, accessibility snapshots and tab metadata.
const fixtures = [
  {
    name: 'local inbox page text',
    input: 'Verify email: http://localhost:8025/verify?token=made-up-email-token#made-up-fragment',
    secrets: ['made-up-email-token', 'made-up-fragment'],
    readable: ['http://localhost:8025/verify?token=<redacted>#<redacted>'],
  },
  {
    name: 'Google accessibility snapshot',
    input: '- link "Continue": https://accounts.google.com/o/oauth2/v2/auth?client_id=made-up-client&state=made-up-ax-state&code_challenge=made-up-ax-challenge&redirect_uri=https%3A%2F%2Flocalhost%2Fcallback',
    secrets: ['made-up-client', 'made-up-ax-state', 'made-up-ax-challenge', 'https%3A'],
    readable: ['https://accounts.google.com/o/oauth2/v2/auth?', 'state=<redacted>', 'code_challenge=<redacted>'],
  },
  {
    name: 'OAuth tab metadata',
    input: [{ id: 'tab-42', title: 'Authorize state=made-up-title-state',
      url: 'https://accounts.google.com/o/oauth2/v2/auth?state=made-up-tab-state&code_challenge=made-up-tab-challenge',
      metadata: { callback: 'https://localhost/callback?code=made-up-callback-code' } }],
    secrets: ['made-up-title-state', 'made-up-tab-state', 'made-up-tab-challenge', 'made-up-callback-code'],
    readable: ['tab-42', 'https://accounts.google.com/o/oauth2/v2/auth?', 'https://localhost/callback?code=<redacted>'],
  },
];

for (const fixture of fixtures) {
  test(`redacts browser output: ${fixture.name}`, () => {
    const before = JSON.stringify(fixture.input);
    const output = redact(fixture.input);
    const text = typeof output === 'string' ? output : JSON.stringify(output);
    for (const secret of fixture.secrets) {
      assert.ok(before.includes(secret), 'fixture really contains the leaked value');
      assert.ok(!text.includes(secret), 'leaked value must be removed');
    }
    for (const readable of fixture.readable) assert.ok(text.includes(readable));
    assert.equal(JSON.stringify(fixture.input), before, 'raw internal value is unchanged');
    assert.deepEqual(redact(output), output, 'safe for explicit redact plus shadow writer');
  });

  test(`frozen runtime shadow and say redact browser output: ${fixture.name}`, () => {
    const emitted = [];
    const repl = Object.freeze({ write(value) { assert.equal(this, repl); emitted.push(value); return 'written'; } });
    const originalWrite = repl.write;
    const output = installChromeRedaction(repl);
    assert.equal(output.mode, 'shadow');
    assert.notEqual(output.nodeRepl, repl);
    assert.equal(output.nodeRepl.write(fixture.input), 'written');
    assert.equal(output.say(fixture.input), 'written');
    assert.equal(installChromeRedaction(output.nodeRepl).nodeRepl.write(fixture.input), 'written');
    assert.equal(repl.write, originalWrite, 'frozen original is untouched');
    assert.deepEqual(emitted, Array(3).fill(redact(fixture.input)));
    for (const secret of fixture.secrets) assert.ok(!JSON.stringify(emitted).includes(secret));
  });
}

test('keeps scheme/host/path/parameter names; removes all query values and fragments', () => {
  const url = 'https://example.org/a/very-long-but-readable-path-abcdefghijklmnop?q=ordinary&empty=&flag#section';
  assert.equal(redact(url), 'https://example.org/a/very-long-but-readable-path-abcdefghijklmnop?q=<redacted>&empty=<redacted>&flag#<redacted>');
  assert.equal(redact('https://example.org/docs/start'), 'https://example.org/docs/start');
  assert.equal(redact('file:///docs/index.html#section'), 'file:///docs/index.html#<redacted>');
  assert.equal(redact('/reset?anything=made-up#section'), '/reset?anything=<redacted>#<redacted>');
  assert.equal(redact('mailto:person@example.org?subject=hello'), 'mailto:person@example.org?subject=<redacted>');
  assert.equal(redact('about:blank#made-up'), 'about:blank#<redacted>');
  assert.equal(redact('https://user:made-up@example.org/'), 'https://<redacted>@example.org/');
});

test('masks secret assignments, object fields, Bearer and opaque/JWT values', () => {
  const values = ['token=short-secret', 'code=123456', 'state: short-secret', 'password="two words"',
    'access_token=short-secret', 'id_token=short-secret', 'code_challenge=short-secret',
    'Authorization: Bearer made.up.value', 'Bearer made-up-bearer',
    'YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXo=', 'abcDEF0123456789/abcDEF0123456789+',
    'eyJhbGciOiJub25lIn0.eyJzdWIiOiJtYWRldXAifQ.c3ludGhldGlj'];
  for (const value of values) {
    const output = redact(value);
    assert.notEqual(output, value);
    assert.ok(output.includes('<redacted>'));
    assert.deepEqual(redact(output), output);
  }
  assert.deepEqual(redact({ token: 'short', accessToken: 'short', password: 1234, nested: { id_token: 'short' }, ok: true }),
    { token: '<redacted>', accessToken: '<redacted>', password: '<redacted>', nested: { id_token: '<redacted>' }, ok: true });
});

test('S1 masks the whole URL fragment when it contains an apostrophe', () => {
  const input = new URL("https://example.org/#prefix'SYNTHETIC-SECRET-SUFFIX").href;
  assert.equal(redact(input), 'https://example.org/#<redacted>');
});

test('S2 quoted assignments honor escapes and preserve valid JSON', () => {
  const input = JSON.stringify({ password: 'prefix"SYNTHETIC-SECRET-SUFFIX' });
  assert.equal(redact(input), '{"password":"<redacted>"}');
  assert.deepEqual(JSON.parse(redact(input)), { password: '<redacted>' });
  assert.equal(redact(String.raw`password='prefix\'SYNTHETIC-SECRET-SUFFIX'`), "password='<redacted>'");
});

test('S3 authorization assignments mask credentials for any scheme', () => {
  assert.equal(redact('Authorization: Basic dXNlcjpwYXNz'), 'Authorization: <redacted>');
  for (const credentials of ['Bearer made.up.value', 'Digest username="made-up", response="made-up"',
    'CustomScheme made-up-credentials']) {
    const output = redact(`Authorization: ${credentials}`);
    assert.equal(output, 'Authorization: <redacted>');
    assert.equal(redact(output), output);
  }
});

test('S4 keeps readable labels while masking token-like assignments', () => {
  for (const input of ['- textbox "ZIP code: optional"', '- textbox "Security code: enter here"',
    'state: ready', 'token: available']) assert.equal(redact(input), input);
  for (const input of ['code=123456', 'code: 123456', 'state: short-secret',
    'token: aBcDeFgHiJkLmNoP', 'password: optional', 'access_token: short']) {
    assert.ok(redact(input).includes('<redacted>'), input);
  }
});

test('S5 structured fields mask short values under ambiguous keys', () => {
  assert.equal(redact(JSON.stringify({ code: '1234', token: 'abcdefghi' })),
    '{"code":"<redacted>","token":"<redacted>"}');
  assert.equal(redact('- textbox "ZIP code: optional"'), '- textbox "ZIP code: optional"');
});

test('S6 unquoted assignments keep masking past literal quotes', () => {
  const output = redact("password=prefix'SYNTHETIC-SECRET-SUFFIX");
  assert.equal(output, 'password=<redacted>');
  assert.doesNotMatch(output, /SYNTHETIC/);
});

test('S7 a label inside a quoted snapshot name keeps its closing quote', () => {
  for (const input of ['- textbox "ZIP code: optional": 90210', "- textbox 'Security code: optional': x"])
    assert.equal(redact(input), input);
  assert.equal(redact('- textbox "Token: aBcDeFgHiJkLmNoP": x'), '- textbox "Token: <redacted>": x');
});

test('S8 a prose apostrophe before an assignment does not end its value early', () => {
  const output = redact("User's password=prefix'SYNTHETIC-SECRET-SUFFIX");
  assert.equal(output, "User's password=<redacted>");
});

test('raw navigation uses real popup URL internally while output stays redacted', async () => {
  const realUrl = 'https://example.org/callback?code=made-up-internal-code';
  const popup = { url: async () => realUrl };
  let navigated;
  const normalTab = { goto: async url => { navigated = url; } };
  const popupUrl = await popup.url();
  await normalTab.goto(popupUrl);
  assert.equal(navigated, realUrl);
  assert.equal(redact({ url: popupUrl }).url, 'https://example.org/callback?code=<redacted>');
});

test('does not invoke inspectors, toJSON or getters; handles cycles and errors', () => {
  const value = { title: 'safe', get password() { throw new Error('must not run'); },
    get page() { throw new Error('must not run'); },
    toJSON() { return 'must not run'; }, [inspect.custom]() { return 'must not run'; } };
  value.self = value;
  const safe = redact(value);
  assert.equal(safe.password, '<redacted>');
  assert.equal(safe.page, '[accessor omitted]');
  assert.equal(safe.self, '[circular]');
  assert.ok(!JSON.stringify(safe).includes('must not run'));
  assert.deepEqual(redact(new Error('https://example.org/?code=made-up')), { name: 'Error', message: 'https://example.org/?code=<redacted>' });
});

test('forwards runtime methods and accessors with their original receiver', async () => {
  const image = { bytes: 'unchanged' };
  const repl = Object.freeze({
    write() {},
    emitImage(value) { assert.equal(this, repl); assert.equal(value, image); return 'image emitted'; },
    get requestMeta() { assert.equal(this, repl); return 'metadata'; },
    cwd: '/work',
  });
  const output = installChromeRedaction(repl);
  assert.equal(await output.nodeRepl.emitImage(image), 'image emitted');
  assert.equal(output.nodeRepl.requestMeta, 'metadata');
  assert.equal(output.nodeRepl.cwd, '/work');
});

test('silently falls back to say when a runtime refuses reflection', () => {
  const emitted = [];
  const runtime = new Proxy({ write: value => emitted.push(value) }, {
    ownKeys() { throw new TypeError('reflection unavailable'); },
  });
  const output = installChromeRedaction(runtime);
  assert.equal(output.mode, 'say');
  assert.equal(output.nodeRepl, runtime);
  output.say(fixtures[0].input);
  assert.deepEqual(emitted, [redact(fixtures[0].input)]);
});

// A plain-Node demonstration; only the redacted fixtures are printed.
if (process.argv.includes('--demo')) {
  for (const fixture of fixtures) console.log(fixture.name, redact(fixture.input));
}
