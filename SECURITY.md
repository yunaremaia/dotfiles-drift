# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities privately by opening a GitHub Security Advisory
or emailing yunare@gmail.com. Do not open public issues for security concerns.

## Security Considerations

- dotfiles-drift reads files from $HOME — ensure symlinks to sensitive files are not followed
- The tool reads file contents for comparison — avoid running on untrusted dotfiles repos
