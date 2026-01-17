# Contributing to DVK

Thank you for your interest in contributing to the Device Verification Kit!

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a branch** for your feature or bugfix
4. **Make your changes** following the guidelines below
5. **Test your changes** thoroughly
6. **Submit a pull request**

---

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/Device-Verification-Kit.git
cd Device-Verification-Kit

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install development dependencies
pip install -r skills/analysis_skill/requirements.txt
pip install -r skills/protocol_detection_skill/requirements.txt
pip install -r skills/transport_session_skill/requirements.txt
```

---

## Code Guidelines

### Python Code

- **Python version**: 3.9+
- **Style**: Follow PEP 8
- **Type hints**: Use type annotations where appropriate
- **Docstrings**: Use triple-quoted docstrings for functions and classes

### Skill Development

When creating or modifying skills:

1. **SKILL.md structure**:
   ```yaml
   ---
   name: skill_name
   description: This skill does X. Requires Y; request missing inputs before Z.
   ---

   # skill_name

   ## Purpose
   [Clear description]

   ## Required Inputs (ask if missing)
   [Table of inputs]

   ## Outputs
   [Table of outputs]

   ## Steps (must follow)
   [Numbered steps]
   ```

2. **Scripts**:
   - Place in `skills/{skill_name}/scripts/`
   - Use `find_dvk_root()` to locate repo root
   - Provide clear error messages
   - Use argparse for CLI arguments

3. **Requirements**:
   - Add `requirements.txt` if skill needs dependencies
   - Pin major versions only: `pandas>=1.5,<3.0`

### Protocol Assets

When adding protocol examples:

1. **Follow schemas**:
   - `spec/schemas/protocol.schema.json`
   - `spec/schemas/commands.schema.json`

2. **Use descriptive names**:
   - `protocol_id`: `device_model_protocol`
   - `command_set_id`: `device_model_protocol_cmds`

3. **Document checksum variants**:
   - For CRC: include poly/init/xorout/refin/refout
   - Add notes for common variants (CRC-16-CCITT, CRC-32, etc.)

---

## Testing

Before submitting a PR:

1. **Test scripts manually**:
   ```bash
   python skills/protocol_decode_skill/scripts/dvk_decode.py --help
   ```

2. **Verify skill metadata**:
   - Check SKILL.md frontmatter format
   - Ensure description follows "This skill..." pattern

3. **Test with Claude Code** (if applicable):
   - Verify skill is registered in `.claude-plugin/plugin.json`
   - Test skill invocation through Claude

---

## Commit Messages

Use clear, descriptive commit messages:

```
Add CRC-32 variant support to protocol schema

- Add params field for poly/init/xorout/refin/refout
- Update protocol.schema.json with CRC variant spec
- Add example protocol with CRC-32
```

**Format**:
- First line: Brief summary (50 chars max)
- Blank line
- Detailed description (if needed)

---

## Pull Request Process

1. **Update documentation**:
   - Update README.md if adding new features
   - Update relevant SKILL.md files

2. **Describe your changes**:
   - What problem does this solve?
   - What approach did you take?
   - Any breaking changes?

3. **Link related issues**:
   - Reference issue numbers: `Fixes #123`

4. **Wait for review**:
   - Address review feedback promptly
   - Keep PRs focused and reasonably sized

---

## Reporting Issues

When reporting bugs or requesting features:

1. **Search existing issues** first
2. **Provide context**:
   - DVK version / commit hash
   - Python version
   - OS and environment details
3. **Include reproduction steps** for bugs
4. **Attach relevant logs** or error messages

---

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Assume good intentions
- Help others learn and grow

---

## Questions?

- Open a [GitHub Discussion](https://github.com/lj123as/Device-Verification-Kit/discussions)
- Check existing issues and PRs
- Review the [README](README.md) and skill documentation

---

Thank you for contributing to DVK! 🚀
