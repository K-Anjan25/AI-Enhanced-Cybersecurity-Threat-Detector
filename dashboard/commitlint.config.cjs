/**
 * Conventional Commits, enforced by the commit-msg pre-commit hook (T-007).
 *
 * This file lives in dashboard/ even though the policy is repo-wide, because
 * commitlint resolves `extends` relative to the config file and the only
 * node_modules in the repository is here. The hook invokes it as
 * `commitlint --config dashboard/commitlint.config.cjs` from the repository root.

 *
 * The scopes are the deployable units plus the planning documents, so a subject
 * line says which part of the system moved:
 *
 *   feat(ml): ..., fix(backend): ..., docs(rules): ..., ci: ..., chore: ...
 */
module.exports = {
    extends: ['@commitlint/config-conventional'],
    rules: {
        'scope-enum': [
            2,
            'always',
            ['backend', 'ml', 'dashboard', 'infra', 'k8s', 'docs', 'ci', 'scripts', 'data'],
        ],
        // A subject that has to be wrapped has not been edited down.
        'header-max-length': [2, 'always', 100],
        'subject-case': [2, 'never', ['start-case', 'pascal-case', 'upper-case']],
    },
};
