"""
Text Processor — handles stateful text transformations during dictation.

This intercepts the transcribed text before it is pasted and applies
"during"-phase transformations (casing, style wraps, block prefixes, lists,
headings, indent, layout inserts, link placeholder) plus the post-pipeline
punctuation/space cleanup.

Cleanup runs on every transcription regardless of whether transforms fired,
so symbol/space hygiene applies universally.
"""

from __future__ import annotations

import re


# Punctuation Whisper sprays around trigger phrases. Stripped from segments
# immediately adjacent to a matched trigger so toggles don't capture the
# stray dot/comma that came from Whisper's pause-detection rather than the
# Person's intent.
_TRIGGER_PUNCT = r"[.,;:!?]"


def _strip_leading_trigger_punct(s: str) -> str:
    """Strip Whisper's leading pause-punctuation from a segment that
    immediately follows a trigger phrase."""
    return re.sub(r"^\s*" + _TRIGGER_PUNCT + r"+\s*", "", s)


def _strip_trailing_trigger_punct(s: str) -> str:
    """Strip Whisper's trailing pause-punctuation from a segment that
    immediately precedes a trigger phrase."""
    stripped = re.sub(r"\s*" + _TRIGGER_PUNCT + r"+(\s*)$", r"\1", s)
    if stripped != s and stripped and not stripped.endswith((" ", "\t", "\n")):
        stripped = stripped + " "
    return stripped


def clean_punctuation_and_spaces(text: str) -> str:
    """Clean up formatting artifacts and normalize symbol spacing."""
    # 1. Collapse multiple spaces (excluding newlines)
    text = re.sub(r"[ \t]+", " ", text)

    # 2. Collapse double commas on the same line
    text = re.sub(r",[^\S\r\n]*,", ",", text)

    # 3. Collapse comma next to period/question/exclamation on the same line
    text = re.sub(r",[^\S\r\n]*([.?!])", r"\1", text)
    text = re.sub(r"([.?!])[^\S\r\n]*,", r"\1", text)

    # 4. Remove spaces/tabs before punctuation (but not newlines)
    text = re.sub(r"[ \t]+([,.?!;:])", r"\1", text)

    # 5. Clean up leading sentence-punctuation/spaces on new lines
    text = re.sub(r"\n[ \t]*[,.?!;:][ \t]*", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)

    # 6. Clean up trailing spaces on lines
    text = re.sub(r"[ \t]+\n", "\n", text)

    # 7. Clean up spaces around newlines generally
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)

    # 8. Collapse spaces inside paired enclosers
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\[\s+", "[", text)
    text = re.sub(r"\s+\]", "]", text)
    text = re.sub(r"\{\s+", "{", text)
    text = re.sub(r"\s+\}", "}", text)
    # Quote pairs: " text " → "text", ' text ' → 'text'.
    # Conservative paired match — won't fire on asymmetric or contractions.
    text = re.sub(r'"\s+([^"\n]*?)\s+"', r'"\1"', text)
    text = re.sub(r"'\s+([^'\n]*?)\s+'", r"'\1'", text)

    # 9. Currency / percent attach to adjacent number
    text = re.sub(r"\$\s+(\d)", r"$\1", text)         # $ 50 → $50
    text = re.sub(r"(\d)\s+%", r"\1%", text)          # 50 % → 50%

    # 10. Clean up leading commas/spaces (on the first line of the entire text)
    text = re.sub(r"^[,\s]+", "", text)

    # 11. Clean up trailing spaces
    text = text.rstrip()
    return text


def _apply_subs_and_macros(text, apply_substitutions_fn, expand_macros_fn):
    """Helper: apply substitutions and macros if provided."""
    if apply_substitutions_fn:
        text = apply_substitutions_fn(text)
    if expand_macros_fn:
        text = expand_macros_fn(text)
    return text


def process_text_transforms(
    text: str,
    voice_commands: dict[str, dict],
    apply_substitutions_fn=None,
    expand_macros_fn=None,
) -> str:
    """Apply stateful text transformations driven by voice commands.

    Supported transform types:
      Casing:   caps_on, caps_off, cap_next
      Style:    bold_on/off, italic_on/off, code_on/off, strikethrough_on/off
      Block:    code_block_on/off, blockquote_on/off
      Lists:    bullet_list_on/off, numbered_list_on/off
      Heading:  heading_h1, heading_h2, heading_h3  (one-shot, next-segment)
      Indent:   indent_in, indent_out               (one-shot, next-segment)
      Layout:   new_line, new_paragraph
      Link:     link                                 (inserts [](url) placeholder)

    Runs substitutions and macros on non-trigger segments before applying
    formatting modes so substitutions don't break voice commands. Always
    finishes with clean_punctuation_and_spaces so spacing artifacts are
    normalized regardless of whether transforms fired.
    """
    if not text:
        return text

    # Filter to only 'transform' actions in the 'during' phase
    transforms = {}
    if voice_commands:
        for trigger, cmd in voice_commands.items():
            if (
                isinstance(cmd, dict)
                and cmd.get("phase") == "during"
                and cmd.get("action") == "transform"
            ):
                transforms[trigger.lower()] = cmd

    # No-transforms path: still apply subs/macros and cleanup so symbol
    # spacing and punctuation hygiene apply universally.
    if not transforms:
        text = _apply_subs_and_macros(text, apply_substitutions_fn, expand_macros_fn)
        return clean_punctuation_and_spaces(text)

    # Sort keys by length descending to match longest triggers first
    keys = sorted(transforms.keys(), key=len, reverse=True)

    # Compile pattern with \s+ between words to handle spacing variations
    escaped_keys = []
    for k in keys:
        words = k.split()
        escaped_keys.append(r"\s+".join(re.escape(w) for w in words))
    pattern = r"\b(" + "|".join(escaped_keys) + r")\b"

    # Split the text by the voice commands
    parts = re.split(pattern, text, flags=re.IGNORECASE)

    # Tag parts so we can lookahead for trailing-strip on data segments
    tagged = []
    for part in parts:
        t_norm = " ".join(part.strip().lower().split())
        if t_norm in transforms:
            tagged.append((True, t_norm, part))
        else:
            tagged.append((False, None, part))

    result = []
    caps_mode = False
    cap_next_mode = False
    bold_mode = False
    italic_mode = False
    code_mode = False
    strike_mode = False
    code_block_mode = False
    quote_mode = False
    bullet_mode = False
    number_mode = False
    number_counter = 0
    heading_next = None    # "#", "##", "###", or None
    indent_next = 0        # net indent change for next segment (in 2-space units)
    prev_was_trigger = False

    for i, (is_trigger, t_norm, part) in enumerate(tagged):
        if is_trigger:
            cmd_type = transforms[t_norm].get("type")
            if cmd_type == "caps_on":
                caps_mode = True
            elif cmd_type == "caps_off":
                caps_mode = False
            elif cmd_type == "cap_next":
                cap_next_mode = True
            elif cmd_type == "bold_on":
                bold_mode = True
            elif cmd_type == "bold_off":
                bold_mode = False
            elif cmd_type == "italic_on":
                italic_mode = True
            elif cmd_type == "italic_off":
                italic_mode = False
            elif cmd_type == "code_on":
                code_mode = True
            elif cmd_type == "code_off":
                code_mode = False
            elif cmd_type == "strikethrough_on":
                strike_mode = True
            elif cmd_type == "strikethrough_off":
                strike_mode = False
            elif cmd_type == "code_block_on":
                code_block_mode = True
                result.append("\n```\n")
            elif cmd_type == "code_block_off":
                code_block_mode = False
                result.append("\n```\n")
            elif cmd_type == "blockquote_on":
                quote_mode = True
            elif cmd_type == "blockquote_off":
                quote_mode = False
            elif cmd_type == "bullet_list_on":
                bullet_mode = True
                number_mode = False
            elif cmd_type == "bullet_list_off":
                bullet_mode = False
            elif cmd_type == "numbered_list_on":
                number_mode = True
                bullet_mode = False
                number_counter = 0
            elif cmd_type == "numbered_list_off":
                number_mode = False
            elif cmd_type == "heading_h1":
                heading_next = "#"
            elif cmd_type == "heading_h2":
                heading_next = "##"
            elif cmd_type == "heading_h3":
                heading_next = "###"
            elif cmd_type == "indent_in":
                indent_next += 1
            elif cmd_type == "indent_out":
                indent_next -= 1
            elif cmd_type == "link":
                result.append("[](url)")
            elif cmd_type == "new_line":
                result.append("\n")
            elif cmd_type == "new_paragraph":
                result.append("\n\n")
            prev_was_trigger = True
            continue

        # It's a normal-text segment.
        # Strip Whisper-injected leading punctuation if the previous part
        # was a trigger.
        if prev_was_trigger:
            part = _strip_leading_trigger_punct(part)
        # Strip Whisper-injected trailing punctuation if the next part is
        # a trigger.
        if i + 1 < len(tagged) and tagged[i + 1][0]:
            part = _strip_trailing_trigger_punct(part)

        prev_was_trigger = False

        # Apply substitutions and macros FIRST so any "during" wrap doesn't
        # capture replaced phrases incorrectly.
        transformed_part = _apply_subs_and_macros(
            part, apply_substitutions_fn, expand_macros_fn
        )

        # Casing
        if caps_mode:
            transformed_part = transformed_part.upper()

        if cap_next_mode and transformed_part.strip():
            def _cap(m):
                return m.group(0).upper()
            transformed_part = re.sub(r"[a-zA-Z]", _cap, transformed_part, count=1)
            cap_next_mode = False

        # Heading (one-shot)
        if heading_next and transformed_part.strip():
            prefix = heading_next + " "
            transformed_part = re.sub(
                r"^(\s*)", lambda m: m.group(1) + prefix, transformed_part, count=1
            )
            heading_next = None

        # Indent (one-shot)
        if indent_next != 0 and transformed_part.strip():
            if indent_next > 0:
                indent_str = "  " * indent_next
                transformed_part = re.sub(
                    r"^(\s*)", lambda m, s=indent_str: m.group(1) + s,
                    transformed_part, count=1
                )
            else:
                pattern_rm = r"^(\s*?)" + (" " * (abs(indent_next) * 2))
                transformed_part = re.sub(pattern_rm, r"\1", transformed_part, count=1)
            indent_next = 0

        # Lists (line-prefix)
        if (bullet_mode or number_mode) and transformed_part.strip():
            lines = transformed_part.split("\n")
            new_lines = []
            for ln in lines:
                if ln.strip():
                    if number_mode:
                        number_counter += 1
                        new_lines.append(f"{number_counter}. {ln.lstrip()}")
                    else:
                        new_lines.append(f"- {ln.lstrip()}")
                else:
                    new_lines.append(ln)
            transformed_part = "\n".join(new_lines)

        # Blockquote (line-prefix)
        if quote_mode and transformed_part.strip():
            lines = transformed_part.split("\n")
            new_lines = [f"> {ln.lstrip()}" if ln.strip() else ln for ln in lines]
            transformed_part = "\n".join(new_lines)

        # Inline wrap modes (bold, italic, code, strikethrough).
        # Code-block mode is line-based (handled by the trigger appends), not
        # an inline wrap, so no wrapper here.
        if transformed_part.strip():
            left_space = len(transformed_part) - len(transformed_part.lstrip())
            right_space = len(transformed_part) - len(transformed_part.rstrip())
            core = transformed_part.strip()

            if code_mode:
                core = f"`{core}`"
            if bold_mode:
                core = f"**{core}**"
            if italic_mode:
                core = f"_{core}_"
            if strike_mode:
                core = f"~~{core}~~"

            transformed_part = (" " * left_space) + core + (" " * right_space)

        result.append(transformed_part)

    final_text = "".join(result)
    return clean_punctuation_and_spaces(final_text)
