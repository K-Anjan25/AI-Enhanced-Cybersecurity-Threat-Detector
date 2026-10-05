/**
 * Stylelint for the dashboard's design tokens (T-007).
 *
 * Two rules from the standard config are turned off deliberately, and both are
 * about index.css — the file that carries the WCAG contrast documentation.
 */
module.exports = {
    extends: ['stylelint-config-standard'],
    rules: {
        // Tailwind directives are not standard CSS at-rules.
        'at-rule-no-unknown': [
            true,
            {
                ignoreAtRules: [
                    'tailwind',
                    'apply',
                    'layer',
                    'config',
                    'screen',
                    'variants',
                    'responsive',
                ],
            },
        ],
        // `@apply` takes a list of utility classes, which is not a valid CSS prelude.
        'at-rule-prelude-no-invalid': [
            true,
            { ignoreAtRules: ['tailwind', 'apply', 'layer', 'screen'] },
        ],
        // The standard config wants `#fff`. `src/theme/tokens.test.ts` extracts the
        // tokens with /#[0-9a-fA-F]{6}/ and asserts the same shape, because the
        // contrast ratios printed next to each value are computed from six digits.
        // Shortening a hex colour here would silently drop that token from the
        // contrast suite rather than fail it, so six digits are required.
        'color-hex-length': null,
        // The tokens are grouped into families under explanatory comments, and the
        // blank line between families is what makes the file scannable.
        'custom-property-empty-line-before': null,
    },
};
