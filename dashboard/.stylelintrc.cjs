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

        // R-27, which rules.md lists as enforced here: "Colours, spacing, radii,
        // and fonts come from the tokens." Spacing and radii are closed at the
        // Tailwind layer (see tailwind.config.js); colours are closed here for CSS,
        // so a stylesheet cannot introduce a literal the token suite never sees.
        'color-no-hex': true,
        'color-named': 'never',
        'function-disallowed-list': ['rgb', 'rgba', 'hsl', 'hsla'],
    },
    overrides: [
        {
            // src/index.css *is* the token layer: it is the one file where a colour
            // literal is the value rather than a bypass, and its shadow token is an
            // alpha colour, which cannot be written as a hex.
            files: ['src/index.css'],
            rules: {
                'color-no-hex': null,
                'color-named': null,
                'function-disallowed-list': null,
            },
        },
    ],
};
