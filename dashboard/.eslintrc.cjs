/**
 * ESLint configuration — rules.md §3.
 *
 * Each rule below cites the rule id it enforces so a suppression cannot be added
 * without seeing what is being waived (R-12, R-21).
 */
module.exports = {
    root: true,
    env: { browser: true, es2022: true },
    parser: '@typescript-eslint/parser',
    parserOptions: { ecmaVersion: 2022, sourceType: 'module', ecmaFeatures: { jsx: true } },
    plugins: ['@typescript-eslint', 'jsx-a11y', 'react-hooks'],
    extends: [
        'eslint:recommended',
        'plugin:@typescript-eslint/recommended',
        'plugin:jsx-a11y/recommended',
    ],
    ignorePatterns: ['dist', 'node_modules', 'coverage'],
    rules: {
        // R-20: TypeScript strict, no `any`.
        '@typescript-eslint/no-explicit-any': 'error',
        '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],

        // R-26 / NFR-09: accessibility is enforced, not advisory.
        'jsx-a11y/alt-text': 'error',
        'jsx-a11y/aria-props': 'error',
        'jsx-a11y/aria-role': 'error',
        'jsx-a11y/no-noninteractive-element-interactions': 'error',

        'react-hooks/rules-of-hooks': 'error',
        'react-hooks/exhaustive-deps': 'warn',

        // R-23: components must not perform network access directly.
        'no-restricted-globals': [
            'error',
            {
                name: 'fetch',
                message:
                    'Use a typed client from src/api/ instead of calling fetch directly (rule R-23).',
            },
        ],
        'no-restricted-imports': [
            'error',
            {
                patterns: [
                    {
                        group: ['axios', 'ky', 'got'],
                        message:
                            'All HTTP access goes through a typed client in src/api/ (rule R-23).',
                    },
                ],
            },
        ],

        // R-28: untrusted strings (log content, explanations) render as text only.
        'no-restricted-syntax': [
            'error',
            {
                selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
                message:
                    'Telemetry content is untrusted and must render as text, never as HTML (rule R-28).',
            },
        ],

        'no-console': ['error', { allow: ['warn', 'error'] }],
        eqeqeq: ['error', 'always'],
    },
    overrides: [
        {
            // R-23: `src/api/` *is* the typed client, so this is the one place
            // `fetch` is allowed to appear.
            files: ['src/api/**'],
            rules: {
                'no-restricted-globals': 'off',
            },
        },
        {
            files: ['**/*.test.ts', '**/*.test.tsx', 'src/test/**'],
            rules: {
                // Tests legitimately assert on console output and reach for globals.
                'no-console': 'off',
                'no-restricted-globals': 'off',
            },
        },
    ],
};
