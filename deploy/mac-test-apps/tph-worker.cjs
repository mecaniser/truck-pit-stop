// Staging adapter: actual Mongo-backed blog queue service, local draft fixture only.
// No cron, source discovery, AI, publication, messaging or production cursors.
process.env.DISABLE_SCHEDULER = 'true';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
assert.equal(process.env.LOCAL_TEST_ONLY, 'true');
const mongoose = require('mongoose');
assert.equal(process.env.SQUARE_ENVIRONMENT, 'sandbox');
const uri = new URL(process.env.MONGO_URI_DEV);
assert.equal(uri.hostname, 'mongo');
assert.equal(uri.pathname, '/tph_local_test');
const source = require.resolve('./backend/services/blogStudioService');
const BlogPost = require('./backend/models/BlogPost');
require.cache[source] = {
  id: source, filename: source, loaded: true,
  exports: {
    INVALID_AI_RESPONSE_CODE: 'LOCAL_TEST_INVALID_RESPONSE',
    createResearchDraft: async ({ topic, trigger, sourceUrls }) => {
      assert.equal(topic, 'LOCALTEST: synthetic worker acceptance');
      assert.equal(trigger, 'manual');
      assert.deepEqual(sourceUrls, []);
      const hash = crypto.createHash('sha256').update(topic).digest('hex');
      const existing = await BlogPost.findOne({ contentFingerprint: hash });
      if (existing) { assert.equal(existing.status, 'draft'); return existing; }
      return BlogPost.create({
        title: 'LOCALTEST: isolated worker receipt', slug: 'localtest-' + hash.slice(0, 24),
        contentFingerprint: hash, bodyMarkdown: '# Synthetic local verification\nNo real research or publication.',
        excerpt: 'Synthetic local content.', metaDescription: 'Synthetic local verification.',
        authorName: 'LOCALTEST Worker', status: 'draft', generatedBy: 'blog_studio', researchSources: [],
      });
    },
  },
};
const Job = require('./backend/models/BlogResearchJob');
const { processNextBlogDraftJob } = require('./backend/services/blogStudioJobService');
async function main() {
  await mongoose.connect(process.env.MONGO_URI_DEV);
  for (;;) {
    const unsafe = await Job.countDocuments({ status: { $in: ['queued', 'running'] }, topic: { $ne: 'LOCALTEST: synthetic worker acceptance' } });
    if (unsafe) throw new Error('Non-synthetic job refused');
    await processNextBlogDraftJob();
    fs.writeFileSync('/tmp/local-worker-health.json', JSON.stringify({ at: Date.now(), synthetic: true }));
    await new Promise(resolve => setTimeout(resolve, 3000));
  }
}
main().catch(() => { console.error('Local test worker refused unsafe state or failed'); process.exit(1); });
