#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sub-agent CCR 模型绑定配置工具
================================
初始化成功后运行本脚本，为 HY127 受管理 Sub-agent 配置模型路由。

用法::

    python3 src/sub_agent_ccr_model_config.py          # 默认 GUI 模式
    python3 src/sub_agent_ccr_model_config.py --cli    # CLI 交互模式
    python3 src/sub_agent_ccr_model_config.py --show   # 仅显示当前绑定

安全约束：
- 不保存或显示 API Key。
- 不写 CCR config.json 或 ~/.claude/settings.json。
- 不删除用户 agent。
"""

import os
import sys
import json
import argparse
from pathlib import Path

# 把仓库根加入 sys.path，使 import ai_providers 可用
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_providers import (
    load_models_config,
    load_agent_bindings,
    save_agent_bindings,
    list_route_options,
    validate_binding,
)
from src.sub_agent_ccr_renderer import render as _render

_CONFIG_PATH = _REPO_ROOT / "ai_models_config.json"
_BINDINGS_PATH = _REPO_ROOT / "agent_role_binding.json"

AGENT_NAMES = ["architect", "implementer", "reviewer", "tester", "docs-writer"]


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _load_config_and_bindings():
    config = load_models_config(str(_CONFIG_PATH))
    bindings_data = load_agent_bindings(str(_BINDINGS_PATH))
    agents = bindings_data.get("agents", {}) if bindings_data else {}
    return config, agents


def _default_binding():
    return {"mode": "inherit", "model": "inherit"}


def _build_options(config):
    """返回 [(display_label, binding_dict), ...] 供 UI 选择。"""
    opts = [("继承当前会话（inherit）", {"mode": "inherit", "model": "inherit"})]
    for o in list_route_options(config):
        provider = o["provider"]
        model_id = o["model_id"]
        label = o["label"]
        requires_ccr = o["requires_ccr"]
        if requires_ccr:
            display = f"[CCR] {label}"
            binding = {"mode": "ccr", "provider": provider, "model": model_id}
        else:
            display = f"[native] {label}"
            binding = {"mode": "native", "model": model_id}
        opts.append((display, binding))
    return opts


# ── CLI 模式 ─────────────────────────────────────────────────────────────────

def show_current(agents):
    print("\n当前绑定：")
    for name in AGENT_NAMES:
        b = agents.get(name, _default_binding())
        mode = b.get("mode", "inherit")
        if mode == "inherit":
            val = "inherit"
        elif mode == "native":
            val = b.get("model", "inherit")
        else:
            val = f"{b.get('provider','?')},{b.get('model','?')}"
        print(f"  {name:<14} {val}")
    print()


def run_cli(config, agents):
    opts = _build_options(config)
    print("\n=== HY127 Sub-agent 模型绑定配置 (CLI 模式) ===")
    print("提示：选择 0 表示保持当前绑定不变；直接回车跳过。\n")
    changed = False
    for name in AGENT_NAMES:
        current = agents.get(name, _default_binding())
        print(f"\n[{name}] 当前：{json.dumps(current, ensure_ascii=False)}")
        for i, (label, _) in enumerate(opts):
            print(f"  {i}) {label}")
        raw = input(f"选择 [0-{len(opts)-1}，回车跳过]: ").strip()
        if not raw:
            continue
        try:
            idx = int(raw)
        except ValueError:
            print("  输入无效，跳过")
            continue
        if idx < 0 or idx >= len(opts):
            print("  超出范围，跳过")
            continue
        _, binding = opts[idx]
        vr = validate_binding(config, binding)
        if not vr.ok:
            print(f"  校验失败: {vr.error}")
            continue
        agents[name] = binding
        changed = True
        print(f"  已设置: {json.dumps(binding, ensure_ascii=False)}")

    if not changed:
        print("\n未作任何修改。")
        return

    import datetime
    data = {
        "version": 1,
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "agents": agents,
    }
    save_agent_bindings(str(_BINDINGS_PATH), data)
    print(f"\n绑定已保存到 {_BINDINGS_PATH}")

    print("\n正在渲染 agent model 字段…")
    result = _render(bindings_path=str(_BINDINGS_PATH))
    print(result.summary())
    if result.errors:
        print("\n⚠ 以下 agent 渲染失败，当前绑定未在 Claude Code 中生效，请检查后重试：")
        for e in result.errors:
            print(f"  {e}")
    else:
        print("\n✓ 所有受管理 agent model 字段已渲染完毕，重启 Claude Code 后生效。")


# ── GUI 模式（tkinter） ───────────────────────────────────────────────────────

def run_gui(config, agents):
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        print("tkinter 不可用，自动切换到 CLI 模式。")
        run_cli(config, agents)
        return

    opts = _build_options(config)
    opt_labels = [l for l, _ in opts]

    root = tk.Tk()
    root.title("HY127 Sub-agent 模型绑定配置")
    root.resizable(True, True)

    # ── 顶部说明 ─────────────────────────────
    note = (
        "本工具只保存 provider/model 标识，不保存 API Key。\n"
        "CCR 模式需已安装并启用 Claude Code Router，且 CCR config 中存在对应 provider/model。\n"
        "[CCR] ark_coding_plan 使用 Coding Plan 专属 API Key，与普通豆包 API 独立，不能混用。\n"
        "ark-code-latest 通过控制台统一管理，切换后约 3-5 分钟生效，不推荐日常快速切换。"
    )
    tk.Label(root, text=note, justify="left", fg="#555", wraplength=700).grid(
        row=0, column=0, columnspan=3, padx=10, pady=8, sticky="w"
    )

    # ── 绑定行 ───────────────────────────────
    combos = {}
    tk.Label(root, text="Agent", font=("", 10, "bold")).grid(row=1, column=0, padx=10, sticky="w")
    tk.Label(root, text="模型路由", font=("", 10, "bold")).grid(row=1, column=1, padx=10, sticky="w")
    tk.Label(root, text="当前绑定", font=("", 10, "bold")).grid(row=1, column=2, padx=10, sticky="w")

    for i, name in enumerate(AGENT_NAMES):
        current = agents.get(name, _default_binding())
        mode = current.get("mode", "inherit")
        if mode == "inherit":
            cur_text = "inherit"
        elif mode == "native":
            cur_text = current.get("model", "inherit")
        else:
            cur_text = f"{current.get('provider','?')},{current.get('model','?')}"

        tk.Label(root, text=name, anchor="w", width=14).grid(row=i + 2, column=0, padx=10, pady=3, sticky="w")
        cb = ttk.Combobox(root, values=opt_labels, state="readonly", width=55)
        cb.set(opt_labels[0])
        cb.grid(row=i + 2, column=1, padx=5, pady=3, sticky="w")
        tk.Label(root, text=cur_text, fg="#333", width=35, anchor="w").grid(
            row=i + 2, column=2, padx=5, sticky="w"
        )
        combos[name] = cb

    status_var = tk.StringVar(value="")
    status_lbl = tk.Label(root, textvariable=status_var, justify="left", fg="#006600", wraplength=700)
    status_lbl.grid(row=len(AGENT_NAMES) + 3, column=0, columnspan=3, padx=10, pady=6, sticky="w")

    def _save_and_render():
        import datetime
        new_agents = dict(agents)
        changed = False
        for name in AGENT_NAMES:
            idx = opt_labels.index(combos[name].get())
            _, binding = opts[idx]
            vr = validate_binding(config, binding)
            if not vr.ok:
                messagebox.showerror("校验失败", f"{name}: {vr.error}")
                return
            if binding != new_agents.get(name):
                new_agents[name] = binding
                changed = True

        if not changed:
            status_var.set("未作任何修改。")
            return

        data = {
            "version": 1,
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "agents": new_agents,
        }
        save_agent_bindings(str(_BINDINGS_PATH), data)
        status_var.set("绑定已保存，渲染中…")
        root.update()

        result = _render(bindings_path=str(_BINDINGS_PATH))
        if result.errors:
            msg = "绑定已保存，但以下 agent 渲染失败，当前绑定未在 Claude Code 生效：\n" + "\n".join(result.errors)
            status_lbl.config(fg="#cc0000")
            status_var.set(msg)
            messagebox.showwarning("渲染部分失败", msg)
        else:
            status_lbl.config(fg="#006600")
            status_var.set(
                f"✓ 完成：{result.summary()}  重启 Claude Code 后生效。"
            )

    btn_frame = tk.Frame(root)
    btn_frame.grid(row=len(AGENT_NAMES) + 2, column=0, columnspan=3, pady=8)
    tk.Button(btn_frame, text="保存并渲染", command=_save_and_render, width=20).pack(side="left", padx=8)
    tk.Button(btn_frame, text="关闭", command=root.destroy, width=10).pack(side="left", padx=4)

    root.mainloop()


# ── 入口 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HY127 Sub-agent 模型绑定配置工具")
    parser.add_argument("--cli",  action="store_true", help="CLI 交互模式（无 GUI）")
    parser.add_argument("--show", action="store_true", help="只显示当前绑定，不修改")
    args = parser.parse_args()

    config, agents = _load_config_and_bindings()

    if args.show:
        show_current(agents)
        return

    if args.cli:
        run_cli(config, agents)
    else:
        run_gui(config, agents)


if __name__ == "__main__":
    main()
