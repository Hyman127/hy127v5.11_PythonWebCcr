#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sub-agent CCR Renderer
======================
从 .claude_templates/agents/*.md 读取基础模板，结合 agent_role_binding.json
中的角色绑定，将 model 字段渲染到 ~/.claude/agents（或 HY127_TEST_AGENTS_DIR）。

CLI 用法::

    python3 src/sub_agent_ccr_renderer.py [--bindings PATH]

    HY127_TEST_AGENTS_DIR=/tmp/test python3 src/sub_agent_ccr_renderer.py --bindings /tmp/bindings.json

安全约束：
- 只写 hy127_managed frontmatter 的受管理 agent。
- 无 hy127_managed 的同名文件跳过，不覆盖。
- 目标路径必须在 agents 目录内（防路径穿越）。
- 原子写入（tmp + rename）。
"""

import os
import re
import sys
import json
import argparse
import tempfile
from pathlib import Path

# 默认路径（相对于本文件上两级目录，即仓库根）
_REPO_ROOT = Path(__file__).parent.parent
_TEMPLATES_DIR = _REPO_ROOT / ".claude_templates" / "agents"
_BINDINGS_PATH = _REPO_ROOT / "agent_role_binding.json"

# 用户级 agents 目录；HY127_TEST_AGENTS_DIR 可覆盖（仅测试用途）
def _get_agents_dir():
    override = os.environ.get("HY127_TEST_AGENTS_DIR", "").strip()
    if override:
        return Path(override)
    home = Path(os.environ.get("USERPROFILE", "") or Path.home())
    return home / ".claude" / "agents"


# ── frontmatter 解析 / 渲染 ──────────────────────────────────────────────────

_FM_RE = re.compile(r"^(---\n)(.*?)(\n---)(.*)", re.DOTALL)


def _parse_frontmatter(text):
    """返回 (fields_dict, raw_fm_text, body) 或 None（解析失败）。"""
    m = _FM_RE.match(text)
    if not m:
        return None
    fm_text = m.group(2)
    body = m.group(4)
    fields = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    return fields, fm_text, body


def _replace_model_field(text, new_model):
    """只替换 frontmatter 中的 model: 行，其余保持原样。"""
    def _repl(m):
        fm_open = m.group(1)   # "---\n"
        fm_body = m.group(2)   # frontmatter 正文
        fm_close = m.group(3)  # "\n---"
        body = m.group(4)      # 文档正文
        if re.search(r"^model:", fm_body, re.MULTILINE):
            fm_body = re.sub(r"^model:.*$", f"model: {new_model}", fm_body, flags=re.MULTILINE)
        else:
            fm_body = fm_body.rstrip() + f"\nmodel: {new_model}"
        return fm_open + fm_body + fm_close + body
    return _FM_RE.sub(_repl, text, count=1)


# ── 绑定 → model 字段 ────────────────────────────────────────────────────────

def _binding_to_model(binding):
    """把 agent_role_binding.json 中的单条绑定转换为 frontmatter model 字段值。"""
    mode = binding.get("mode", "inherit")
    if mode == "inherit":
        return "inherit"
    if mode == "native":
        return binding.get("model", "inherit")
    if mode == "ccr":
        provider = binding.get("provider", "")
        model = binding.get("model", "")
        if provider and model:
            return f"{provider},{model}"
    return "inherit"


# ── 原子写入 ─────────────────────────────────────────────────────────────────

def _write_atomic(path, content):
    tmp = str(path) + ".hy127.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, str(path))


# ── 主渲染逻辑 ───────────────────────────────────────────────────────────────

class RenderResult:
    def __init__(self):
        self.created = []
        self.updated = []
        self.skipped = []
        self.errors = []

    @property
    def ok(self):
        return len(self.errors) == 0

    def summary(self):
        lines = [
            f"created={len(self.created)} updated={len(self.updated)} "
            f"skipped={len(self.skipped)} errors={len(self.errors)}"
        ]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        return "\n".join(lines)


def render(bindings_path=None, agents_dir=None, templates_dir=None):
    """执行渲染，返回 RenderResult。"""
    result = RenderResult()

    if templates_dir is None:
        templates_dir = _TEMPLATES_DIR
    templates_dir = Path(templates_dir)

    if agents_dir is None:
        agents_dir = _get_agents_dir()
    agents_dir = Path(agents_dir)

    if bindings_path is None:
        bindings_path = _BINDINGS_PATH
    bindings_path = Path(bindings_path)

    # 加载绑定
    if bindings_path.exists():
        try:
            raw = json.loads(bindings_path.read_text(encoding="utf-8"))
            bindings = raw.get("agents", raw)
        except Exception as e:
            result.errors.append(f"bindings 解析失败: {e}")
            return result
    else:
        bindings = {}

    # 确保目标目录存在
    try:
        agents_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        result.errors.append(f"无法创建 agents 目录 {agents_dir}: {e}")
        return result

    agents_dir_resolved = agents_dir.resolve()

    # 枚举模板
    if not templates_dir.exists():
        result.errors.append(f"模板目录不存在: {templates_dir}")
        return result

    for tmpl_path in sorted(templates_dir.glob("*.md")):
        agent_name = tmpl_path.stem
        target_path = agents_dir / tmpl_path.name
        target_resolved = target_path.resolve() if target_path.exists() else (agents_dir_resolved / tmpl_path.name)

        # 路径穿越检查
        try:
            target_resolved.relative_to(agents_dir_resolved)
        except ValueError:
            result.errors.append(f"路径穿越拒绝: {tmpl_path.name}")
            continue

        # 读取模板内容
        try:
            tmpl_text = tmpl_path.read_text(encoding="utf-8")
        except Exception as e:
            result.errors.append(f"读取模板失败 {tmpl_path.name}: {e}")
            continue

        # 验证模板 frontmatter
        parsed = _parse_frontmatter(tmpl_text)
        if parsed is None:
            result.errors.append(f"模板 frontmatter 解析失败: {tmpl_path.name}")
            continue
        tmpl_fields, _, _ = parsed
        if tmpl_fields.get("name") != agent_name:
            result.errors.append(f"模板 name 字段与文件名不符: {tmpl_path.name}")
            continue
        if not tmpl_fields.get("hy127_managed", "").startswith(agent_name + "-v"):
            result.errors.append(f"模板 hy127_managed 字段格式不符: {tmpl_path.name}")
            continue

        # 计算目标 model 值
        binding = bindings.get(agent_name, {"mode": "inherit", "model": "inherit"})
        new_model = _binding_to_model(binding)
        rendered_text = _replace_model_field(tmpl_text, new_model)

        # 目标文件不存在 → 创建
        if not target_path.exists():
            try:
                _write_atomic(target_path, rendered_text)
                result.created.append(agent_name)
            except Exception as e:
                result.errors.append(f"创建 {agent_name} 失败: {e}")
            continue

        # 目标文件存在 → 检查 reparse point（Linux 上检查 symlink）
        if target_path.is_symlink():
            result.skipped.append(f"{agent_name} (symlink)")
            continue

        # 检查是否为受管理文件
        try:
            existing_text = target_path.read_text(encoding="utf-8")
        except Exception as e:
            result.errors.append(f"读取目标 {agent_name} 失败: {e}")
            continue

        existing_parsed = _parse_frontmatter(existing_text)
        if existing_parsed is None:
            result.skipped.append(f"{agent_name} (无 frontmatter)")
            continue

        existing_fields, _, _ = existing_parsed
        existing_managed = existing_fields.get("hy127_managed", "")
        if not existing_managed.startswith(agent_name + "-v"):
            result.skipped.append(f"{agent_name} (用户自定义，无 hy127_managed)")
            continue

        # 受管理文件 → 渲染（只更新 model 字段）
        updated_text = _replace_model_field(existing_text, new_model)
        if updated_text == existing_text:
            result.skipped.append(f"{agent_name} (model 未变化)")
            continue

        try:
            _write_atomic(target_path, updated_text)
            result.updated.append(agent_name)
        except Exception as e:
            result.errors.append(f"更新 {agent_name} 失败: {e}")

    return result


# ── CLI 入口 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="渲染 HY127 受管理 Sub-agent 的 model 字段"
    )
    parser.add_argument(
        "--bindings",
        default=str(_BINDINGS_PATH),
        help="agent_role_binding.json 路径（默认：仓库根目录）",
    )
    parser.add_argument(
        "--templates-dir",
        default=str(_TEMPLATES_DIR),
        help=".claude_templates/agents 路径（默认：仓库根目录）",
    )
    args = parser.parse_args()

    agents_dir = _get_agents_dir()
    result = render(
        bindings_path=args.bindings,
        agents_dir=agents_dir,
        templates_dir=args.templates_dir,
    )
    print(result.summary())
    if not result.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
