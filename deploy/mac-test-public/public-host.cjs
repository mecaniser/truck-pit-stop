// Build-time adapter for this synthetic web image only. Native production source
// and worker images remain pinned and are never edited by this script.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = 'backend/server.js';
const before = fs.readFileSync(source, 'utf8');
const needle = '    if (!origin) return callback(null, true);';
assert.equal(before.split(needle).length, 2, 'Expected one native CORS entry point');
assert.equal(before.includes('https://tph-test.elisprotech.com'), false, 'Test origin already present');
assert.equal(process.env.SQUARE_ENVIRONMENT, 'sandbox');
const addition = `
    // This isolated test web may accept only its exact HTTPS browser origin.
    if (process.env.LOCAL_TEST_ONLY === 'true'
        && process.env.SQUARE_ENVIRONMENT === 'sandbox'
        && origin === 'https://tph-test.elisprotech.com') {
      return callback(null, true);
    }
`;
fs.writeFileSync(source, before.replace(needle, needle + addition));
console.log('Added guarded exact HTTPS test origin to synthetic web CORS');
