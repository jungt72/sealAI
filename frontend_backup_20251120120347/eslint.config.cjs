const {
    defineConfig,
    globalIgnores,
} = require("eslint/config");

const globals = require("globals");
const tsParser = require("@typescript-eslint/parser");
const typescriptEslint = require("@typescript-eslint/eslint-plugin");
const react = require("eslint-plugin-react");
const reactHooks = require("eslint-plugin-react-hooks");
const nextNext = require("@next/eslint-plugin-next");

const {
    fixupPluginRules,
    fixupConfigRules,
} = require("@eslint/compat");

const js = require("@eslint/js");

const {
    FlatCompat,
} = require("@eslint/eslintrc");

const compat = new FlatCompat({
    baseDirectory: __dirname,
    recommendedConfig: js.configs.recommended,
    allConfig: js.configs.all
});

module.exports = defineConfig([{
    languageOptions: {
        globals: {
            ...globals.browser,
            ...globals.node,
        },

        parser: tsParser,
        ecmaVersion: 2023,
        sourceType: "module",

        parserOptions: {
            ecmaFeatures: {
                jsx: true,
            },

            project: undefined,
        },
    },

    plugins: {
        "@typescript-eslint": typescriptEslint,
        react,
        "react-hooks": fixupPluginRules(reactHooks),
        "@next/next": nextNext,
    },

    extends: fixupConfigRules(compat.extends(
        "eslint:recommended",
        "plugin:@typescript-eslint/recommended",
        "plugin:react/recommended",
        "plugin:react-hooks/recommended",
        "plugin:@next/next/core-web-vitals-legacy",
    )),

    settings: {
        react: {
            version: "detect",
        },

        "import/resolver": {
            node: {
                extensions: [".js", ".jsx", ".ts", ".tsx"],
            },

            typescript: {},
        },
    },

    rules: {
        "react/react-in-jsx-scope": "off",
        "react/prop-types": "off",
        "react/jsx-uses-react": "off",
        "@next/next/no-img-element": "off",
        "@next/next/no-html-link-for-pages": "off",
        "react/no-unknown-property": "off",
        "no-empty": "off",
        "@typescript-eslint/no-explicit-any": "off",
        "@typescript-eslint/explicit-module-boundary-types": "off",

        "@typescript-eslint/no-unused-vars": ["warn", {
            argsIgnorePattern: "^_",
            varsIgnorePattern: "^_",
        }],

        "react-hooks/exhaustive-deps": "warn",
        "react-hooks/set-state-in-effect": "off",
    },
}, globalIgnores([
    "**/.next/",
    "**/out/",
    "**/build/",
    "**/dist/",
    "**/node_modules/",
    "**/next-env.d.ts",
])]);
