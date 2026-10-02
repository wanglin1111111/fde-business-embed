#!/usr/bin/env python3
"""validate.py — fde-business-embed AI 落地试点计划七维校验器

输入: AI 落地试点计划 JSON（schema 见 tests/sample_good.json）
  {
    "decision": {
      "specific_issue": "具体的、AI 还没跑通的业务环节",  // 非空
      "ai_not_running": true,                              // 该环节当前 AI 未跑通
      "motivation": "real_problem"                         // real_problem | curiosity
    },
    "scene_card": {
      "process": "业务环节（一句话）",
      "current_cost": "现状耗时/人力",
      "data_access": "数据在哪、能不能拿",
      "tried_and_blocked": "试过什么、卡在哪",
      "quantifiable_success": "成功长什么样（可量化指标）",
      "pusher": "business_owner"                           // business_owner | it
    },
    "scope": {
      "stages": ["环节名"],                                 // 试点环节（必须恰好 1 个）
      "high_freq": true,
      "low_risk": true,
      "result_judgeable": true
    },
    "fallback": {
      "reviewer": "谁复核",
      "release_condition": "什么条件放行",
      "rollback_point": "错了回退到哪",
      "in_process_doc": true,                              // 兜底已写进流程文档
      "automation_before_samples": false                   // 跑够样本前不得自动化
    },
    "prototype": {
      "prompt_template": true,                             // 提示词/模板
      "test_records": 10,                                  // 真实数据测试条数（≥10）
      "comparison_metrics": true,                          // 准确率/耗时对比数字
      "accepted_by": "user"                                // user(使用方) | tech(技术方)
    },
    "replication": {
      "second_stage": "",                                  // 第二环节（空=停在试点）
      "first_stage_metrics": {
        "accuracy": 0.8,                                   // 数值
        "adoption": 0.9                                    // 数值
      },
      "copy_full_flow": true                               // 复制=全流程重走
    }
  }

七维校验（任一 FAIL → exit 1）：
  D1 决策前置: specific_issue 非空 且 ai_not_running=true 且 motivation=real_problem
     （凭热情/凭"想学习"立项 = FAIL）
  D2 场景卡五必填: process/current_cost/data_access/tried_and_blocked/
     quantifiable_success 全非空 + pusher ∈ {business_owner, it}
     （缺一 = 问题没被真实击中）
  D3 拆到最小: stages 恰好 1 个 且 high_freq 且 low_risk 且 result_judgeable
     （试点只能一个环节；三条件缺一不切）
  D4 兜底先于自动化: reviewer/release_condition/rollback_point 全非空 且
     in_process_doc=true 且 automation_before_samples=false
     （兜底靠自觉 = FAIL；没跑够样本就自动化 = FAIL）
  D5 小样三件套+使用方评判: prompt_template=true 且 test_records≥10 且
     comparison_metrics=true 且 accepted_by=user
     （技术方自评不算闭环）
  D6 量化再复制: second_stage 非空时，first_stage_metrics 的 accuracy 与 adoption
     必须为 (0,1] 数值 且 copy_full_flow=true（搬模板不算复制）；
     second_stage 为空 = 停在试点，合规豁免
  D7 谁在推: pusher 必须为 business_owner（纯 IT 推动 = 活不过两个季度）

退出码：0=通过 / 1=有缺陷 / 2=文件/格式错误
"""
import json
import sys

NUMERIC_METRICS = ("accuracy", "adoption")


def fail(checks, code, msg):
    checks.append(("FAIL", code, msg))


def ok(checks, code, msg):
    checks.append(("OK", code, msg))


def is_nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def validate(plan):
    checks = []

    # D1 决策前置
    dc = plan.get("decision") or {}
    if not is_nonempty_str(dc.get("specific_issue")):
        fail(checks, "D1", "specific_issue 缺失——没有具体的业务环节就不立项")
    elif dc.get("ai_not_running") is not True:
        fail(checks, "D1", "ai_not_running=false——该环节 AI 已跑通，不属于落地试点")
    elif dc.get("motivation") != "real_problem":
        fail(checks, "D1", f"motivation={dc.get('motivation')!r}——凭热情/想学习立项，须 real_problem")
    else:
        ok(checks, "D1", "决策前置通过（具体环节+AI 未跑通+真实问题驱动）")

    # D2 场景卡五必填
    sc = plan.get("scene_card") or {}
    missing = [k for k in ("process", "current_cost", "data_access",
                           "tried_and_blocked", "quantifiable_success")
               if not is_nonempty_str(sc.get(k))]
    pusher = sc.get("pusher")
    if missing:
        fail(checks, "D2", f"场景卡缺: {missing}——五项必填缺一=问题没被真实击中")
    elif pusher not in ("business_owner", "it"):
        fail(checks, "D2", f"pusher={pusher!r} 非法——须声明 business_owner/it")
    else:
        ok(checks, "D2", f"场景卡五必填齐全（推动方: {pusher}）")

    # D3 拆到最小
    sc2 = plan.get("scope") or {}
    stages = sc2.get("stages") or []
    if len(stages) != 1:
        fail(checks, "D3", f"试点环节数={len(stages)}——拆到最小：试点只能一个环节")
    else:
        bad = [k for k in ("high_freq", "low_risk", "result_judgeable")
               if sc2.get(k) is not True]
        if bad:
            fail(checks, "D3", f"选环节三条件缺: {bad}——高频+低风险+结果可判定缺一不切")
        else:
            ok(checks, "D3", f"拆到最小（{stages[0]}：高频+低风险+结果可判定）")

    # D4 兜底先于自动化
    fb = plan.get("fallback") or {}
    missing_fb = [k for k in ("reviewer", "release_condition", "rollback_point")
                  if not is_nonempty_str(fb.get(k))]
    if missing_fb:
        fail(checks, "D4", f"兜底机制缺: {missing_fb}——谁复核/什么条件放行/回退到哪，必须写进流程")
    elif fb.get("in_process_doc") is not True:
        fail(checks, "D4", "in_process_doc=false——兜底没写进流程文档=靠自觉，不许去人工")
    elif fb.get("automation_before_samples") is not False:
        fail(checks, "D4", "automation_before_samples=true——跑够样本前不得自动化")
    else:
        ok(checks, "D4", "兜底机制齐全且先于自动化（写进流程）")

    # D5 小样三件套+使用方评判
    pt = plan.get("prototype") or {}
    tr = pt.get("test_records")
    issues = []
    if pt.get("prompt_template") is not True:
        issues.append("prompt_template 缺")
    if not isinstance(tr, int) or tr < 10:
        issues.append(f"test_records={tr!r} 须≥10 条真实数据")
    if pt.get("comparison_metrics") is not True:
        issues.append("comparison_metrics 缺（准确率/耗时对比数字）")
    if pt.get("accepted_by") != "user":
        issues.append(f"accepted_by={pt.get('accepted_by')!r}——验收人必须使用方，技术方自评不算闭环")
    if issues:
        fail(checks, "D5", "小样纪律缺: " + "；".join(issues))
    else:
        ok(checks, "D5", f"小样三件套齐全（{tr} 条真实数据，使用方验收）")

    # D6 量化再复制
    rp = plan.get("replication") or {}
    second = rp.get("second_stage")
    if is_nonempty_str(second):
        fm = rp.get("first_stage_metrics") or {}
        bad_m = []
        for k in NUMERIC_METRICS:
            v = fm.get(k)
            if not isinstance(v, (int, float)) or not (0 < v <= 1):
                bad_m.append(k)
        if bad_m:
            fail(checks, "D6", f"第二环节「{second}」立项但第一环节数字缺: {bad_m}——没数字禁止复制，停在试点")
        elif rp.get("copy_full_flow") is not True:
            fail(checks, "D6", "copy_full_flow=false——复制=全流程重走，搬模板不算复制")
        else:
            ok(checks, "D6", f"量化再复制合规（{second}：accuracy={fm['accuracy']}, adoption={fm['adoption']}，全流程复制）")
    else:
        ok(checks, "D6", "停在试点（无第二环节），合规")

    # D7 谁在推
    if pusher == "it":
        fail(checks, "D7", "pusher=it——纯 IT 推动业务不用=活不过两个季度，须业务负责人推动")
    elif pusher == "business_owner":
        ok(checks, "D7", "推动方=业务负责人")
    else:
        ok(checks, "D7", "推动方未声明，由 D2 处理")

    return checks


def main():
    if len(sys.argv) != 2:
        print("usage: python validate.py plan.json", file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 无法读取/解析: {e}", file=sys.stderr)
        return 2
    if not isinstance(plan, dict):
        print("ERROR: 顶层必须是 JSON 对象", file=sys.stderr)
        return 2

    checks = validate(plan)
    fails = [c for c in checks if c[0] == "FAIL"]
    for status, code, msg in checks:
        if status == "FAIL":
            print(f"[{code}] FAIL {msg}")
    print(f"== {len(checks) - len(fails)} OK / {len(fails)} FAIL ==")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
