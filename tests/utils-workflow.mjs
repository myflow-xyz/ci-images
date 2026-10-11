import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const require = createRequire(import.meta.url);
// Reuse the YAML parser already pinned in the Markdown verification bundle.
const { load } = await import(require.resolve('js-yaml', {
  paths: [path.join(root, 'images/node/markdownlint')]
}));
const workflow = name => load(readFileSync(path.join(root, '.github/workflows', name), 'utf8'));

test('manual utility qualification has a separate dispatch and runner concurrency group', () => {
  const utility = workflow('utils-test.yml');
  assert.deepEqual(Object.keys(utility.on), ['workflow_dispatch']);
  assert.equal(utility.on.workflow_dispatch.inputs.utils_runner.required, true);
  assert.match(utility.on.workflow_dispatch.inputs.utils_runner.description, /label/i);
  assert.deepEqual(Object.keys(utility.jobs), ['utils-runner']);
  const job = utility.jobs['utils-runner'];
  assert.deepEqual(job['runs-on'], ['self-hosted', '${{ inputs.utils_runner }}']);
  assert.match(utility.concurrency.group, /inputs\.utils_runner/);
  assert.doesNotMatch(utility.concurrency.group, /github\.ref/);
  assert.equal(utility.concurrency['cancel-in-progress'], false);
  assert.notEqual(utility.concurrency.group, workflow('images.yml').concurrency.group);
  for (const scope of [utility.permissions, job.permissions]) {
    assert.ok(Object.values(scope ?? {}).every(permission => permission === 'read'));
  }
  const actions = job.steps.filter(step => step.uses);
  assert.equal(actions.length, 1);
  assert.match(actions[0].uses, /^actions\/checkout@[0-9a-f]{40}$/);
  assert.equal(actions[0].with.ref, undefined, 'the image selector must not override checkout');
  assert.equal(actions[0].with['persist-credentials'], false);
  const commands = job.steps.map(step => step.run ?? '').join('\n');
  assert.doesNotMatch(commands, /build-local-image|publish-image|release-images|promote-images|docker push/);
  assert.match(commands, /tests\/utils-docker\.sh/);
  assert.match(commands, /CI_UTILS_TEST_IMAGE_STORE=classic tests\/utils-docker\.sh/);
});

test('normal image CI retains both utility stores without manual utility routing', () => {
  const images = workflow('images.yml');
  assert.equal(images.on.workflow_dispatch?.inputs, undefined);
  assert.equal(images.jobs['utils-runner'], undefined);
  assert.doesNotMatch(JSON.stringify(images), /utils_runner|utils_image/);
  const commands = images.jobs.smoke.steps.map(step => step.run ?? '').join('\n');
  assert.match(commands, /tests\/utils-docker\.sh/);
  assert.match(commands, /CI_UTILS_TEST_IMAGE_STORE=classic tests\/utils-docker\.sh/);
});
