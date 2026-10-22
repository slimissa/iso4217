'use strict';

// ESLint flat config for the JavaScript wrapper (v1.9.0, F27). ESLint 9 and later will not run without one.
// Deliberately small: it checks what a CommonJS file of this size can get wrong (undefined or unused names, loose
// equality, var). `x != null` is allowed: index.js uses it on purpose to mean "neither null nor undefined".
// Only index.js is linted. `files` in package.json keeps this file out of the npm tarball.
module.exports = [
  {
    files: ['index.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {
        require: 'readonly',
        module: 'writable',
        __dirname: 'readonly',
        process: 'readonly',
        console: 'readonly',
      },
    },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': 'error',
      'no-redeclare': 'error',
      'no-var': 'error',
      'prefer-const': 'error',
      eqeqeq: ['error', 'always', { null: 'ignore' }],
    },
  },
];
