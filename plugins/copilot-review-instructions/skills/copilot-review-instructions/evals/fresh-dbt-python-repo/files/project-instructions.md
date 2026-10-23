# Data Platform – project-wide Copilot review instructions
(Exported from Azure DevOps > Project settings > Copilot code review. Applies to all repos in the project.)

## Security
- Flag hardcoded secrets, connection strings, tokens or passwords.
- Use parameterized queries; never build SQL with string concatenation or f-strings from user input.

## Python
- Use snake_case for functions and variables and PascalCase for classes.
- Every public function must have a docstring.
- Add type hints to all function signatures.

## Testing
- New features need unit tests.

## SQL
- Write SQL keywords in lowercase.
