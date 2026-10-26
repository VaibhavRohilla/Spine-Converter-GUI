import tseslint from 'typescript-eslint';
export default tseslint.config(
 {ignores:['viewer/src/generated/**','viewer/.runtime/**','viewer/dist/**','viewer/test-results/**']},
 ...tseslint.configs.recommended,
 {files:['viewer/src/**/*.ts'],rules:{'@typescript-eslint/no-explicit-any':'error','no-restricted-syntax':['error',{selector:'TSUnknownKeyword',message:'Use a validated domain type in viewer code; narrow caught values at the boundary.'}],'@typescript-eslint/no-unused-vars':['error',{argsIgnorePattern:'^_'}]}}
);
