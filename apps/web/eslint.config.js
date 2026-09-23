import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // A cor volta a ser literal na primeira tela escrita com pressa. O token existe
      // para que contraste e tom sejam revisáveis num lugar só, em src/styles.css.
      'no-restricted-syntax': [
        'error',
        {
          selector: 'Literal[value=/#[0-9a-fA-F]{6}\\b/]',
          message:
            'Use um token de cor de src/styles.css em vez de um literal hexadecimal.',
        },
        {
          selector: 'TemplateElement[value.raw=/#[0-9a-fA-F]{6}\\b/]',
          message:
            'Use um token de cor de src/styles.css em vez de um literal hexadecimal.',
        },
        {
          // A sombra do invólucro guardava a última cor crua da interface, fora do alcance
          // da regra acima porque era rgba e não hexadecimal.
          selector: 'Literal[value=/rgba?\\(/]',
          message: 'Use um token de cor ou de sombra de src/styles.css em vez de rgb/rgba.',
        },
        {
          selector: 'TemplateElement[value.raw=/rgba?\\(/]',
          message: 'Use um token de cor ou de sombra de src/styles.css em vez de rgb/rgba.',
        },
      ],
    },
  },
)
