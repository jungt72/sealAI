/**
 * Legacy ESLint config compatible with ESLint 9 while avoiding
 * the circular JSON serialization issues introduced by the new
 * eslint-config-next flat config. Keep this file until the repo
 * migrates to eslint.config.mjs.
 */

module.exports = {
  root: true,
  env: {
    browser: true,
    node: true,
    es2023: true,
  },
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaFeatures: { jsx: true },
    ecmaVersion: 2023,
    sourceType: "module",
    project: undefined,
  },
  plugins: ["@typescript-eslint", "react", "react-hooks", "@next/next"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react/recommended",
    "plugin:react-hooks/recommended",
    "plugin:@next/next/core-web-vitals-legacy",
  ],
  settings: {
    react: { version: "detect" },
    "import/resolver": {
      node: { extensions: [".js", ".jsx", ".ts", ".tsx"] },
      typescript: {},
    },
  },
  ignorePatterns: [
    ".next/",
    "out/",
    "build/",
    "dist/",
    "node_modules/",
    "next-env.d.ts",
  ],
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
    "@typescript-eslint/no-unused-vars": [
      "warn",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
    "react-hooks/exhaustive-deps": "warn",
    "react-hooks/set-state-in-effect": "off",
  },
};
