import tseslint from 'typescript-eslint';
export default tseslint.config(
 {ignores:['viewer/src/generated/**','viewer/.runtime/**','viewer/dist/**','viewer/test-results/**']},
 ...tseslint.configs.recommended,
 {files:['viewer/src/**/*.ts'],rules:{'@typescript-eslint/no-explicit-any':'error','@typescript-eslint/no-unused-vars':['error',{argsIgnorePattern:'^_'}]}}
);
