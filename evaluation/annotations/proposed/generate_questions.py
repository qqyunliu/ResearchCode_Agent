#!/usr/bin/env python3
"""Generate 36 pilot evaluation questions for RuoYi-Vue dataset."""

import json
import hashlib
from datetime import datetime, timezone

COMMIT_SHA = "41720e624c5a668c7d3777835e4c87095a7a1dfd"
REPO_ID = "ruoyi-vue"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def fingerprint(text: str) -> str:
    """SHA256 of normalized question text, first 8 chars."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]


def q(seq, task_type, lang, diff, question, answerable,
      eval_layers, gold_entities=None, gold_nodes=None, gold_edges=None,
      gold_files=None, required_claims=None, forbidden_claims=None,
      expected_uncertainties=None, special_sample_type=None, notes="",
      source_files=None, source_lines=None):
    """Build one question dict."""
    return {
        "dataset_version": "1.0",
        "question_id": f"ruoyi-{task_type.lower()}-{seq:04d}",
        "question_fingerprint": fingerprint(question),
        "repo_id": REPO_ID,
        "commit_sha": COMMIT_SHA,
        "split": "development",
        "task_type": task_type,
        "language": lang,
        "difficulty": diff,
        "question": question,
        "answerable": answerable,
        "question_origin": "machine_generated",
        "gold_status": "machine_proposed",
        "evaluation_layers": eval_layers,
        "expected_task_type": task_type,
        "gold_entities": gold_entities or [],
        "gold_nodes": gold_nodes or [],
        "gold_edges": gold_edges or [],
        "gold_files": gold_files or [],
        "required_claims": required_claims or [],
        "forbidden_claims": forbidden_claims or [],
        "expected_uncertainties": expected_uncertainties or [],
        "special_sample_type": special_sample_type or [],
        "annotation": {
            "annotator": "question_generator_A",
            "reviewer": "",
            "review_status": "needs_review",
            "notes": notes
        },
        "provenance": {
            "source_files": source_files or [],
            "source_lines": source_lines or [],
            "generation_method": "code_inspection",
            "created_at": NOW
        }
    }


questions = []

# ============================================================
# CODE_QA questions (12): zh=6, en=6
# easy=4, medium=5, hard=3
# answerable=9, unanswerable=3
# ============================================================

# --- CODE_QA #1: zh, easy, answerable ---
questions.append(q(
    seq=1, task_type="CODE_QA", lang="zh", diff="easy",
    question="用户登录的接口定义在哪个控制器中？该接口的HTTP方法和路径是什么？",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["SysLoginController", "POST /login"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java"],
    required_claims=[
        "登录接口在SysLoginController中定义",
        "HTTP方法为POST，路径为/login"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java:56-65"],
    notes="Basic CODE_QA: single controller identification"
))

# --- CODE_QA #2: en, easy, answerable ---
questions.append(q(
    seq=2, task_type="CODE_QA", lang="en", diff="easy",
    question="Which controller handles the user list query API, and what is its request mapping path prefix?",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["SysUserController", "GET /system/user/list"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    required_claims=[
        "SysUserController handles user list queries",
        "The class-level RequestMapping is /system/user",
        "The list endpoint uses GET method"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:41-66"],
    special_sample_type=["distractor_entity"],
    notes="Basic CODE_QA: controller + path prefix identification. Distractor: SysProfileController also handles user-related APIs"
))

# --- CODE_QA #3: zh, easy, answerable ---
questions.append(q(
    seq=3, task_type="CODE_QA", lang="zh", diff="easy",
    question="获取验证码图片的API端点路径是什么？该功能在哪个类中实现？",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["CaptchaController", "GET /captchaImage"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java"],
    required_claims=[
        "验证码API路径为GET /captchaImage",
        "实现在CaptchaController类的getCode方法中"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java:45-93"],
    notes="Basic CODE_QA: API path identification from controller"
))

# --- CODE_QA #4: en, easy, answerable ---
questions.append(q(
    seq=4, task_type="CODE_QA", lang="en", diff="easy",
    question="Where is the department tree structure API implemented for the user management page?",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["SysUserController", "GET /system/user/deptTree"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    required_claims=[
        "The dept tree API is at GET /system/user/deptTree",
        "It is defined in SysUserController, not SysDeptController",
        "The method calls deptService.selectDeptTreeList"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:250-255"],
    notes="Tests same-name entity disambiguation: deptTree in SysUserController vs SysDeptController"
))

# --- CODE_QA #5: zh, medium, answerable ---
questions.append(q(
    seq=5, task_type="CODE_QA", lang="zh", diff="medium",
    question="角色管理模块提供了哪些API接口？请列出所有HTTP方法和路径，以及各自对应的操作。",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "SysRoleController",
        "GET /system/role/list",
        "POST /system/role/export",
        "GET /system/role/{roleId}",
        "POST /system/role",
        "PUT /system/role",
        "PUT /system/role/dataScope",
        "PUT /system/role/changeStatus",
        "DELETE /system/role/{roleIds}",
        "GET /system/role/optionselect",
        "GET /system/role/authUser/allocatedList",
        "GET /system/role/authUser/unallocatedList",
        "PUT /system/role/authUser/cancel",
        "PUT /system/role/authUser/cancelAll",
        "PUT /system/role/authUser/selectAll",
        "GET /system/role/deptTree/{roleId}"
    ],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java"],
    required_claims=[
        "角色管理共有15个API接口",
        "包含列表查询、导出、详情、新增、修改、数据权限、状态修改、删除、选择框、用户授权等接口",
        "所有接口定义在SysRoleController中"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java:37-254"],
    notes="Medium CODE_QA: requires enumerating all APIs in a controller"
))

# --- CODE_QA #6: en, medium, answerable ---
questions.append(q(
    seq=6, task_type="CODE_QA", lang="en", diff="medium",
    question="What security validations are performed when creating a new scheduled job? List all the checks done in the add endpoint.",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysJobController", "POST /monitor/job"],
    gold_files=["ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java"],
    required_claims=[
        "Cron expression validity is checked via CronUtils.isValid",
        "RMI invocation is blocked",
        "LDAP/LDAPS invocation is blocked",
        "HTTP/HTTPS invocation is blocked",
        "A blacklist of forbidden strings (JOB_ERROR_STR) is checked",
        "A whitelist check is performed via ScheduleUtils.whiteList",
        "The @PreAuthorize annotation requires monitor:job:add permission"
    ],
    source_files=["ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java"],
    source_lines=["ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java:80-111"],
    notes="Medium CODE_QA: detailed logic within a controller method"
))

# --- CODE_QA #7: zh, medium, answerable (no exact names in question) ---
questions.append(q(
    seq=7, task_type="CODE_QA", lang="zh", diff="medium",
    question="前端缓存管理页面中，有哪些请求使用了动态URL拼接（路径中包含变量）？为什么这些请求在静态分析时无法被自动匹配到对应的后端接口？",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "GET /monitor/cache/getKeys/{cacheName}",
        "GET /monitor/cache/getValue/{cacheName}/{cacheKey}",
        "DELETE /monitor/cache/clearCacheName/{cacheName}",
        "DELETE /monitor/cache/clearCacheKey/{cacheKey}"
    ],
    gold_files=[
        "ruoyi-ui/src/api/monitor/cache.js",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java"
    ],
    required_claims=[
        "cache.js中有4个请求使用了字符串拼接构造URL",
        "这些请求的URL中包含运行时变量如cacheName和cacheKey",
        "静态分析无法在编译时确定完整的URL路径，因此标记为dynamic_url"
    ],
    expected_uncertainties=["前端扫描器无法解析JavaScript字符串拼接来还原完整API路径"],
    source_files=["ruoyi-ui/src/api/monitor/cache.js"],
    source_lines=[
        "ruoyi-ui/src/api/monitor/cache.js:20-25",
        "ruoyi-ui/src/api/monitor/cache.js:28-33",
        "ruoyi-ui/src/api/monitor/cache.js:36-41",
        "ruoyi-ui/src/api/monitor/cache.js:44-49"
    ],
    notes="Tests understanding of dynamic URL limitation in static analysis. No exact entity names in question."
))

# --- CODE_QA #8: en, medium, answerable (no exact names in question) ---
questions.append(q(
    seq=8, task_type="CODE_QA", lang="en", diff="medium",
    question="How does the user password change flow work for the personal profile page? Describe the validation steps and which controller handles it.",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "SysProfileController",
        "PUT /system/user/profile/updatePwd"
    ],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java"],
    required_claims=[
        "The password change is handled in SysProfileController.updatePwd at PUT /system/user/profile/updatePwd",
        "It validates old password matches using SecurityUtils.matchesPassword",
        "It checks new password is different from old password",
        "The new password is encrypted with SecurityUtils.encryptPassword",
        "After success, it updates the LoginUser cache via tokenService.setLoginUser",
        "It sets the pwdUpdateDate to current time"
    ],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java",
        "ruoyi-ui/src/api/system/user.js"
    ],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java:91-119"],
    notes="No exact class/method names in the question text."
))

# --- CODE_QA #9: zh, medium, answerable ---
questions.append(q(
    seq=9, task_type="CODE_QA", lang="zh", diff="medium",
    question="系统中有哪些控制器继承了BaseController？BaseController提供了哪些通用方法？",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "BaseController",
        "SysUserController",
        "SysRoleController",
        "SysDeptController",
        "SysMenuController",
        "SysConfigController",
        "SysNoticeController",
        "SysPostController",
        "SysProfileController",
        "SysJobController",
        "GenController"
    ],
    gold_files=[
        "ruoyi-common/src/main/java/com/ruoyi/common/core/controller/BaseController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"
    ],
    required_claims=[
        "多数系统控制器都继承了BaseController",
        "BaseController提供startPage分页、getDataTable封装、success/error/toAjax等响应方法",
        "CaptchaController和SysLoginController不继承BaseController",
        "CommonController也继承了BaseController"
    ],
    source_files=["ruoyi-common/src/main/java/com/ruoyi/common/core/controller/BaseController.java"],
    source_lines=["ruoyi-common/src/main/java/com/ruoyi/common/core/controller/BaseController.java"],
    notes="Tests understanding of class hierarchy. No exact file names in question."
))

# --- CODE_QA #10: en, hard, answerable (logout - unmatchable) ---
questions.append(q(
    seq=10, task_type="CODE_QA", lang="en", diff="hard",
    question="How does the system implement user logout? Why does the frontend POST /logout request not appear as a mapped endpoint in any controller class?",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["LogoutSuccessHandlerImpl"],
    gold_files=[
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java",
        "ruoyi-ui/src/api/login.js"
    ],
    required_claims=[
        "Logout is handled by Spring Security's built-in LogoutFilter, not a custom controller",
        "SecurityConfig configures .logout(logout -> logout.logoutUrl('/logout').logoutSuccessHandler(logoutSuccessHandler))",
        "LogoutSuccessHandlerImpl implements LogoutSuccessHandler",
        "On logout, it deletes the user's token cache via tokenService.delLoginUser",
        "It records the logout event asynchronously via AsyncManager",
        "The static scanner cannot detect this endpoint because it is configured via Spring Security DSL, not @RequestMapping"
    ],
    expected_uncertainties=["The exact logout URL is configured in SecurityConfig DSL and not via annotation-based mapping"],
    source_files=[
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java"
    ],
    source_lines=[
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java:111",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java:39-52"
    ],
    notes="Hard CODE_QA: explains the unmatched /logout finding. Involves dynamic/unprovable behavior."
))

# --- CODE_QA #11: zh, hard, answerable (same-name entities) ---
questions.append(q(
    seq=11, task_type="CODE_QA", lang="zh", diff="hard",
    question="系统中用户管理相关的API分布在两个不同的控制器中，一个处理管理后台的用户CRUD操作，另一个处理用户的个人信息修改。请说明这两个控制器的路径前缀分别是什么，各自处理哪些请求方法？",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "SysUserController",
        "SysProfileController",
        "GET /system/user/list",
        "POST /system/user",
        "PUT /system/user",
        "DELETE /system/user/{userIds}",
        "PUT /system/user/resetPwd",
        "PUT /system/user/changeStatus",
        "GET /system/user/profile",
        "PUT /system/user/profile",
        "PUT /system/user/profile/updatePwd",
        "POST /system/user/profile/avatar"
    ],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java"
    ],
    required_claims=[
        "SysUserController的路径前缀为/system/user",
        "SysProfileController的路径前缀为/system/user/profile",
        "SysUserController处理用户列表、新增、修改、删除、密码重置、状态修改、授权角色、部门树等管理操作",
        "SysProfileController处理个人信息查看/修改、个人密码修改、头像上传",
        "两者共用相同的路径前缀部分(/system/user)，但Profile是更深的子路径"
    ],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java"
    ],
    source_lines=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:41",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java:35"
    ],
    notes="Hard CODE_QA: same-name/similar entity disambiguation. Tests understanding of path prefix overlap."
))

# --- CODE_QA #12: en, hard, unanswerable ---
questions.append(q(
    seq=12, task_type="CODE_QA", lang="en", diff="hard",
    question="Does the system provide an API endpoint for exporting user data to PDF format? If so, which controller and method implement it?",
    answerable=False,
    eval_layers=["routing", "retrieval"],
    gold_entities=[],
    gold_files=[],
    required_claims=[],
    forbidden_claims=[
        "There is a PDF export endpoint",
        "Any controller has a method that generates PDF"
    ],
    expected_uncertainties=[
        "The system only supports Excel export via ExcelUtil, not PDF export",
        "No PDF generation library or endpoint exists in the scanned codebase"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:68-76"],
    notes="Unanswerable CODE_QA: system only has Excel export, no PDF. Tests uncertainty expression."
))

# ============================================================
# Additional CODE_QA unanswerable questions
# ============================================================

# We need 3 unanswerable in CODE_QA. We have #12. Let me add 2 more.
# But wait, I already have 12 CODE_QA. Let me adjust.
# Actually I need to re-check my distribution: CODE_QA=12 total.
# I have questions 1-12 all as CODE_QA. That's correct.
# Of these: unanswerable = #12 only = 1. I need 3.
# Let me convert some to unanswerable.

# Let me re-plan. I'll overwrite some questions.

# Actually let me redo: I have 12 CODE_QA, need answerable=9, unanswerable=3.
# Currently: #1-11 answerable (11), #12 unanswerable (1).
# I need to make #9 and another one unanswerable, or adjust differently.

# Better approach: let me add unanswerable questions separately and adjust numbering.
# Let me restructure the entire list. I'll build it as a clean list.

questions = []  # Reset

# ================================================================
# CODE_QA (12): zh=6, en=6, easy=4, medium=5, hard=3
# answerable=9, unanswerable=3
# ================================================================

# 1. zh, easy, answerable
questions.append(q(
    seq=1, task_type="CODE_QA", lang="zh", diff="easy",
    question="用户登录的接口定义在哪个控制器中？该接口的HTTP方法和路径是什么？",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["SysLoginController", "POST /login"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java"],
    required_claims=["登录接口在SysLoginController中定义", "HTTP方法为POST，路径为/login"],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java:56-65"]
))

# 2. en, easy, answerable
questions.append(q(
    seq=2, task_type="CODE_QA", lang="en", diff="easy",
    question="Which controller handles the user list query API, and what is its request mapping path prefix?",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["SysUserController", "GET /system/user/list"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    required_claims=["SysUserController handles user list queries", "The class-level RequestMapping is /system/user"],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:41-66"]
))

# 3. zh, easy, answerable
questions.append(q(
    seq=3, task_type="CODE_QA", lang="zh", diff="easy",
    question="验证码生成的API端点路径是什么？该功能在哪个类中实现？",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["CaptchaController", "GET /captchaImage"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java"],
    required_claims=["验证码API路径为GET /captchaImage", "实现在CaptchaController类的getCode方法中"],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/common/CaptchaController.java:45-93"]
))

# 4. en, easy, answerable (distractor: deptTree could be in DeptController)
questions.append(q(
    seq=4, task_type="CODE_QA", lang="en", diff="easy",
    question="Where is the department tree structure API implemented for the user management page?",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["SysUserController", "GET /system/user/deptTree"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    required_claims=["The dept tree API is at GET /system/user/deptTree", "It is in SysUserController, not SysDeptController"],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:250-255"],
    special_sample_type=["distractor_entity", "same_name_entity"],
    notes="Distractor entity: SysDeptController also exists but doesn't have deptTree endpoint for user page. Same-name: deptTree could logically belong to either controller."
))

# 5. zh, medium, answerable
questions.append(q(
    seq=5, task_type="CODE_QA", lang="zh", diff="medium",
    question="角色管理模块提供了哪些API接口？请列出所有HTTP方法和路径，以及各自对应的操作类型。",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysRoleController", "GET /system/role/list", "POST /system/role", "PUT /system/role", "DELETE /system/role/{roleIds}"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java"],
    required_claims=["角色管理共有15个API接口", "所有接口定义在SysRoleController中"],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java:37-254"]
))

# 6. en, medium, answerable
questions.append(q(
    seq=6, task_type="CODE_QA", lang="en", diff="medium",
    question="What security validations are performed when creating a new scheduled job? List all the checks done in the creation endpoint.",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysJobController", "POST /monitor/job"],
    gold_files=["ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java"],
    required_claims=[
        "Cron expression validity is checked",
        "RMI, LDAP, HTTP invocations are blocked",
        "Forbidden strings are checked",
        "Whitelist validation is performed",
        "Requires monitor:job:add permission"
    ],
    source_files=["ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java"],
    source_lines=["ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java:80-111"]
))

# 7. zh, medium, answerable (no exact names - dynamic URLs)
questions.append(q(
    seq=7, task_type="CODE_QA", lang="zh", diff="medium",
    question="前端缓存管理页面中，有哪些请求使用了动态URL拼接？为什么这些请求在静态分析时无法被自动匹配到后端接口？",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["GET /monitor/cache/getKeys/{cacheName}", "GET /monitor/cache/getValue/{cacheName}/{cacheKey}",
                   "DELETE /monitor/cache/clearCacheName/{cacheName}", "DELETE /monitor/cache/clearCacheKey/{cacheKey}"],
    gold_files=["ruoyi-ui/src/api/monitor/cache.js", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java"],
    required_claims=["cache.js中有4个请求使用了字符串拼接构造URL", "静态分析无法解析JavaScript字符串拼接"],
    source_files=["ruoyi-ui/src/api/monitor/cache.js"],
    source_lines=["ruoyi-ui/src/api/monitor/cache.js:20-49"],
    notes="No exact entity names in question. Tests dynamic URL understanding."
))

# 8. en, medium, answerable (no exact names)
questions.append(q(
    seq=8, task_type="CODE_QA", lang="en", diff="medium",
    question="How does the user password change flow work for the personal profile page? Describe the validation steps and which handler processes it.",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysProfileController", "PUT /system/user/profile/updatePwd"],
    gold_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java"],
    required_claims=[
        "Password change is at PUT /system/user/profile/updatePwd",
        "Validates old password matches",
        "Checks new password differs from old",
        "Encrypts new password with BCrypt",
        "Updates LoginUser cache"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java:91-119"],
    special_sample_type=["distractor_entity"],
    notes="No exact class/method names in question. Distractor: SysUserController.resetPwd also resets passwords but is admin-only, not personal profile."
))

# 9. zh, medium, unanswerable (no exact names)
questions.append(q(
    seq=9, task_type="CODE_QA", lang="zh", diff="medium",
    question="系统中是否有处理短信发送功能的API接口？如果有，请说明其实现位置。",
    answerable=False,
    eval_layers=["routing", "retrieval"],
    gold_entities=[],
    gold_files=[],
    required_claims=[],
    forbidden_claims=["存在短信发送API", "有任何控制器实现了短信发送方法"],
    expected_uncertainties=["系统中不存在短信发送相关的API接口", "扫描到的所有控制器中均未发现短信发送功能"],
    notes="Unanswerable CODE_QA: no SMS feature exists. No exact names in question."
))

# 10. en, hard, answerable (logout mystery)
questions.append(q(
    seq=10, task_type="CODE_QA", lang="en", diff="hard",
    question="How does the system implement user logout? Why does the frontend logout request not appear as a mapped endpoint in any controller class?",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["LogoutSuccessHandlerImpl"],
    gold_files=[
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java",
        "ruoyi-ui/src/api/login.js"
    ],
    required_claims=[
        "Logout is handled by Spring Security LogoutFilter",
        "Configured in SecurityConfig via .logout() DSL",
        "LogoutSuccessHandlerImpl deletes token cache and logs the event",
        "Static scanner cannot detect this because it uses DSL not annotations"
    ],
    expected_uncertainties=["The logout URL is configured declaratively in Spring Security, not via @RequestMapping"],
    source_files=[
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java"
    ],
    source_lines=[
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java:111",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java:39-52"
    ],
    notes="Hard: explains the unmatched /logout finding."
))

# 11. zh, hard, answerable (same-name entities)
questions.append(q(
    seq=11, task_type="CODE_QA", lang="zh", diff="hard",
    question="系统中用户管理相关的API分布在两个不同的控制器中，一个处理管理后台的用户CRUD，另一个处理个人信息修改。请说明它们的路径前缀分别是什么，各自包含哪些HTTP方法和路径？",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysUserController", "SysProfileController"],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java"
    ],
    required_claims=[
        "SysUserController路径前缀为/system/user",
        "SysProfileController路径前缀为/system/user/profile",
        "SysUserController包含list, export, importData, getInfo, add, edit, remove, resetPwd, changeStatus, authRole, deptTree",
        "SysProfileController包含profile, updateProfile, updatePwd, avatar"
    ],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java"
    ],
    source_lines=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:41",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysProfileController.java:35"
    ],
    special_sample_type=["same_name_entity", "distractor_entity"],
    notes="Hard: same-prefix entity disambiguation. Both controllers share /system/user prefix. Distractor: SysUserController and SysProfileController have overlapping path prefix."
))

# 12. en, hard, unanswerable
questions.append(q(
    seq=12, task_type="CODE_QA", lang="en", diff="hard",
    question="Does the system provide an API endpoint for exporting user data to PDF format? If so, which controller and method implement it?",
    answerable=False,
    eval_layers=["routing", "retrieval"],
    gold_entities=[],
    gold_files=[],
    required_claims=[],
    forbidden_claims=["There is a PDF export endpoint", "Any controller generates PDF output"],
    expected_uncertainties=["The system only supports Excel export via ExcelUtil", "No PDF generation library or endpoint exists"],
    notes="Unanswerable: only Excel export exists, no PDF."
))

# We need 1 more unanswerable. Let me check: #9 unanswerable, #12 unanswerable = 2. Need 3.
# Let me change one more. I'll make a 13th... no, CODE_QA must be exactly 12.
# I need to make one of the answerable ones unanswerable. Let me adjust #9 to medium and add another unanswerable.
# Actually wait: I have 12 questions. #9 is unanswerable (zh, medium), #12 is unanswerable (en, hard).
# That's 2 unanswerable. I need 3. Let me replace one answerable with an unanswerable.

# Let me reconsider. I'll change the seq to accommodate. Since I have the full list as Python objects, let me just
# replace one of the medium answerable ones.

# Replace #8 (en, medium, answerable) -> keep it. Instead, I'll restructure.
# I have: easy=4(answerable), medium=5(4 answerable + 1 unanswerable), hard=3(2 answerable + 1 unanswerable)
# That's: answerable=4+4+2=10, unanswerable=0+1+1=2. I need 9 answerable, 3 unanswerable.
# So I need one more unanswerable. Let me convert one medium answerable to unanswerable.

# Actually let me just accept the current 12 and add an unanswerable en medium instead of one answerable.
# I'll adjust: change question #8 to unanswerable.

questions[7] = q(
    seq=8, task_type="CODE_QA", lang="en", diff="medium",
    question="Is there a dedicated API for batch-importing user data from a JSON file? Which endpoint accepts JSON-format user imports?",
    answerable=False,
    eval_layers=["routing", "retrieval"],
    gold_entities=[],
    gold_files=[],
    required_claims=[],
    forbidden_claims=["There is a JSON batch import endpoint", "Any endpoint accepts JSON for user import"],
    expected_uncertainties=[
        "The system supports user import only via Excel files (POST /system/user/importData with MultipartFile)",
        "No JSON-based batch import API exists"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:78-88"],
    special_sample_type=["distractor_entity"],
    notes="Unanswerable: import only supports Excel, not JSON. Distractor: importData endpoint exists but for Excel only."
)

# Now: answerable = #1,2,3,4,5,6,7,10,11 = 9, unanswerable = #8,9,12 = 3.
# zh = #1,3,5,7,9,11 = 6, en = #2,4,6,8,10,12 = 6.
# easy = #1,2,3,4 = 4, medium = #5,6,7,8,9 = 5, hard = #10,11,12 = 3.


# ================================================================
# TRACE_CHAIN (12): zh=6, en=6
# easy=2, medium=6, hard=4
# answerable=9, unanswerable=3
# At least 4 include frontend requests (REQUESTS_API)
# At least 4 verify Controller -> Service
# At least 3 verify HTTP method/path mismatch or unresolved request
# ================================================================

# 13. zh, easy, answerable - 1-hop frontend -> backend
questions.append(q(
    seq=13, task_type="TRACE_CHAIN", lang="zh", diff="easy",
    question="前端调用登录接口POST /login时，请求最终到达后端的哪个控制器和哪个方法？",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["POST /login", "SysLoginController", "SysLoginController.login"],
    gold_nodes=["POST /login", "SysLoginController.login"],
    gold_edges=[{"type": "REQUESTS_API", "from": "POST /login (login.js)", "to": "POST /login (SysLoginController)"}],
    gold_files=[
        "ruoyi-ui/src/api/login.js",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java"
    ],
    required_claims=["前端login.js中POST /login请求到达SysLoginController.login方法"],
    source_files=["ruoyi-ui/src/api/login.js", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java"],
    source_lines=["ruoyi-ui/src/api/login.js:11-19", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java:56-65"],
    notes="1-hop frontend->backend trace. Frontend request included."
))

# 14. en, easy, answerable - 1-hop frontend -> backend
questions.append(q(
    seq=14, task_type="TRACE_CHAIN", lang="en", diff="easy",
    question="Trace the frontend request for creating a new department. Which frontend API function sends the request, and which backend controller method receives it?",
    answerable=True,
    eval_layers=["routing", "retrieval"],
    gold_entities=["POST /system/dept", "SysDeptController", "SysDeptController.add"],
    gold_nodes=["POST /system/dept (dept.js)", "SysDeptController.add"],
    gold_edges=[{"type": "REQUESTS_API", "from": "POST /system/dept (dept.js)", "to": "POST /system/dept (SysDeptController)"}],
    gold_files=[
        "ruoyi-ui/src/api/system/dept.js",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java"
    ],
    required_claims=["Frontend dept.js sends POST /system/dept", "Backend SysDeptController.add receives it"],
    source_files=["ruoyi-ui/src/api/system/dept.js", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java"],
    source_lines=["ruoyi-ui/src/api/system/dept.js:30-37", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java:75-86"],
    notes="1-hop frontend->backend. Frontend request included."
))

# 15. zh, medium, answerable - Controller -> Service chain
questions.append(q(
    seq=15, task_type="TRACE_CHAIN", lang="zh", diff="medium",
    question="当用户管理页面调用GET /system/user/list接口时，请求从控制器到服务层的调用链是怎样的？控制器方法调用了哪个Service接口和哪个方法？",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysUserController", "SysUserController.list", "ISysUserService", "ISysUserService.selectUserList"],
    gold_nodes=["SysUserController.list", "ISysUserService.selectUserList"],
    gold_edges=[{"type": "CALLS_METHOD", "from": "SysUserController.list", "to": "ISysUserService.selectUserList"}],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java"
    ],
    required_claims=[
        "SysUserController.list调用userService.selectUserList",
        "userService是ISysUserService接口的实现"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:59-66"],
    special_sample_type=["distractor_entity"],
    notes="Controller->Service trace. 2-hop chain. Distractor: ISysRoleService also injected in same controller."
))

# 16. en, medium, answerable - Controller -> Service chain
questions.append(q(
    seq=16, task_type="TRACE_CHAIN", lang="en", diff="medium",
    question="When the frontend calls PUT /system/role to update a role, which controller method handles it and which service method does it invoke? Also, what additional action is taken after a successful update?",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysRoleController", "SysRoleController.edit", "ISysRoleService", "TokenService"],
    gold_nodes=["SysRoleController.edit", "ISysRoleService.updateRole", "TokenService.refreshPermissionByRoleId"],
    gold_edges=[
        {"type": "CALLS_METHOD", "from": "SysRoleController.edit", "to": "ISysRoleService.updateRole"},
        {"type": "CALLS_METHOD", "from": "SysRoleController.edit", "to": "TokenService.refreshPermissionByRoleId"}
    ],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java"
    ],
    required_claims=[
        "SysRoleController.edit handles PUT /system/role",
        "It calls roleService.updateRole",
        "After success, it calls tokenService.refreshPermissionByRoleId to refresh online users' permissions"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java:110-134"],
    special_sample_type=["distractor_entity"],
    notes="Controller->Service chain with post-action. Distractor: SysPermissionService also injected in the same controller."
))

# 17. zh, medium, answerable - frontend -> backend -> service (2-hop)
questions.append(q(
    seq=17, task_type="TRACE_CHAIN", lang="zh", diff="medium",
    question="从前端调用新增通知公告接口到后端处理完成，完整的调用链是怎样的？请说明前端函数、后端控制器方法、以及服务层方法的调用顺序。",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["POST /system/notice", "SysNoticeController", "SysNoticeController.add", "ISysNoticeService", "ISysNoticeService.insertNotice"],
    gold_nodes=["POST /system/notice (notice.js)", "SysNoticeController.add", "ISysNoticeService.insertNotice"],
    gold_edges=[
        {"type": "REQUESTS_API", "from": "POST /system/notice (notice.js)", "to": "POST /system/notice (SysNoticeController)"},
        {"type": "CALLS_METHOD", "from": "SysNoticeController.add", "to": "ISysNoticeService.insertNotice"}
    ],
    gold_files=[
        "ruoyi-ui/src/api/system/notice.js",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java"
    ],
    required_claims=[
        "前端notice.js中addNotice发送POST /system/notice",
        "SysNoticeController.add接收请求",
        "调用noticeService.insertNotice完成插入"
    ],
    source_files=["ruoyi-ui/src/api/system/notice.js", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java"],
    source_lines=["ruoyi-ui/src/api/system/notice.js:22-27", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java:65-72"],
    notes="2-hop: frontend -> controller -> service. Frontend request included."
))

# 18. en, medium, answerable - unresolved dynamic URL
questions.append(q(
    seq=18, task_type="TRACE_CHAIN", lang="en", diff="medium",
    question="The frontend cache management module calls a function to retrieve cache keys for a given cache name. Can the static index trace this request to its backend endpoint? If not, why?",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["GET /monitor/cache/getKeys/{cacheName}", "CacheController"],
    gold_nodes=["GET /monitor/cache/getKeys/{cacheName} (cache.js)", "CacheController.getKeys"],
    gold_edges=[],
    gold_files=[
        "ruoyi-ui/src/api/monitor/cache.js",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java"
    ],
    required_claims=[
        "The frontend function listCacheKey constructs the URL dynamically: '/monitor/cache/getKeys/' + cacheName",
        "The backend endpoint is GET /monitor/cache/getKeys/{cacheName} in CacheController",
        "The static index marks this as dynamic_url and cannot automatically create a REQUESTS_API relation"
    ],
    expected_uncertainties=["The static scanner flagged this as dynamic_url so the REQUESTS_API link is not stored"],
    source_files=["ruoyi-ui/src/api/monitor/cache.js", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java"],
    source_lines=["ruoyi-ui/src/api/monitor/cache.js:20-25", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java:80-86"],
    notes="Tests understanding of unresolved dynamic URL. Frontend request included."
))

# 19. zh, medium, answerable - Controller -> Service for menu
questions.append(q(
    seq=19, task_type="TRACE_CHAIN", lang="zh", diff="medium",
    question="前端请求获取菜单路由信息时(GET /getRouters)，后端控制器方法调用了哪些服务方法？请追踪完整调用链。",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["GET /getRouters", "SysLoginController", "ISysMenuService"],
    gold_nodes=["GET /getRouters (menu.js)", "SysLoginController.getRouters", "ISysMenuService.selectMenuTreeByUserId", "ISysMenuService.buildMenus"],
    gold_edges=[
        {"type": "REQUESTS_API", "from": "GET /getRouters (menu.js)", "to": "GET /getRouters (SysLoginController)"},
        {"type": "CALLS_METHOD", "from": "SysLoginController.getRouters", "to": "ISysMenuService.selectMenuTreeByUserId"},
        {"type": "CALLS_METHOD", "from": "SysLoginController.getRouters", "to": "ISysMenuService.buildMenus"}
    ],
    gold_files=[
        "ruoyi-ui/src/api/menu.js",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java"
    ],
    required_claims=[
        "SysLoginController.getRouters先调用menuService.selectMenuTreeByUserId获取菜单树",
        "再调用menuService.buildMenus构建路由"
    ],
    source_files=["ruoyi-ui/src/api/menu.js", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java"],
    source_lines=["ruoyi-ui/src/api/menu.js:5", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java:101-107"],
    notes="2-hop chain with multiple service calls. Frontend request included."
))

# 20. en, medium, unanswerable - unmatched /logout
questions.append(q(
    seq=20, task_type="TRACE_CHAIN", lang="en", diff="medium",
    question="Trace the call chain for the frontend POST /logout request. Which backend controller method handles this request?",
    answerable=False,
    eval_layers=["routing", "retrieval"],
    gold_entities=["LogoutSuccessHandlerImpl"],
    gold_nodes=[],
    gold_edges=[],
    gold_files=["ruoyi-ui/src/api/login.js", "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java"],
    required_claims=[],
    forbidden_claims=["A controller class maps POST /logout via @PostMapping or @RequestMapping"],
    expected_uncertainties=[
        "POST /logout is not handled by any controller - it is configured via Spring Security LogoutFilter",
        "The static index has no DEFINES_API entity for /logout",
        "LogoutSuccessHandlerImpl handles the logout response but is not a controller"
    ],
    source_files=["ruoyi-ui/src/api/login.js", "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java"],
    source_lines=["ruoyi-ui/src/api/login.js:52-56", "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java:111"],
    notes="Unanswerable trace: /logout is unmatched. HTTP method/path mismatch verification. Frontend request included."
))

# 21. zh, hard, answerable - multi-hop with same-name (getInfo in multiple controllers)
questions.append(q(
    seq=21, task_type="TRACE_CHAIN", lang="zh", diff="hard",
    question="系统中存在多个名为getInfo的方法，分别在哪些控制器中定义？它们各自对应的API路径是什么？前端调用GET /getInfo时会到达哪个方法？",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysLoginController.getInfo", "CacheController.getInfo", "SysUserController.getInfo"],
    gold_nodes=["GET /getInfo (SysLoginController)", "GET /monitor/cache (CacheController)", "GET /system/user/{userId} (SysUserController)"],
    gold_edges=[{"type": "REQUESTS_API", "from": "GET /getInfo (login.js)", "to": "GET /getInfo (SysLoginController)"}],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"
    ],
    required_claims=[
        "SysLoginController.getInfo映射GET /getInfo",
        "CacheController.getInfo映射GET /monitor/cache",
        "SysUserController.getInfo映射GET /system/user/{userId}",
        "前端GET /getInfo到达SysLoginController.getInfo"
    ],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java"
    ],
    source_lines=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysLoginController.java:72-94",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java:48-71"
    ],
    special_sample_type=["same_name_entity", "distractor_entity"],
    notes="Hard: same-name method disambiguation across controllers. Three getInfo methods exist. Distractor: CacheController.getInfo and SysUserController.getInfo are wrong targets."
))

# 22. en, hard, answerable - HTTP method mismatch check
questions.append(q(
    seq=22, task_type="TRACE_CHAIN", lang="en", diff="hard",
    question="The frontend user.js file sends a DELETE request to /system/user/{userId}. Can you trace this to the backend? Also check: does the same path /system/user/ with a GET method go to the same controller method or a different one?",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "DELETE /system/user/{userIds}",
        "GET /system/user/{userId}",
        "SysUserController"
    ],
    gold_nodes=["DELETE /system/user/{userIds} (user.js)", "GET /system/user/{userId} (user.js)", "SysUserController.remove", "SysUserController.getInfo"],
    gold_edges=[
        {"type": "REQUESTS_API", "from": "DELETE /system/user/{userId} (user.js)", "to": "DELETE /system/user/{userIds} (SysUserController)"},
        {"type": "REQUESTS_API", "from": "GET /system/user/{userId} (user.js)", "to": "GET /system/user/{userId} (SysUserController)"}
    ],
    gold_files=[
        "ruoyi-ui/src/api/system/user.js",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"
    ],
    required_claims=[
        "DELETE /system/user/{userId} maps to SysUserController.remove",
        "GET /system/user/{userId} maps to SysUserController.getInfo",
        "They are different controller methods despite sharing the same URL path pattern",
        "The HTTP method determines which handler is invoked"
    ],
    source_files=["ruoyi-ui/src/api/system/user.js", "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"],
    source_lines=[
        "ruoyi-ui/src/api/system/user.js:40-44",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:100-117",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:177-187"
    ],
    special_sample_type=["same_name_entity"],
    notes="Hard: HTTP method/path verification. Same path /system/user/{id}, different HTTP methods -> different handlers. Tests method overloading via HTTP verbs."
))

# 23. zh, hard, unanswerable - trace to non-existent API
questions.append(q(
    seq=23, task_type="TRACE_CHAIN", lang="zh", diff="hard",
    question="请追踪前端调用POST /system/user/batchDelete请求的完整链路，该请求在后端由哪个控制器方法处理？",
    answerable=False,
    eval_layers=["routing", "retrieval"],
    gold_entities=[],
    gold_nodes=[],
    gold_edges=[],
    gold_files=[],
    required_claims=[],
    forbidden_claims=["POST /system/user/batchDelete是一个有效的后端API", "存在专门处理batchDelete的控制器方法"],
    expected_uncertainties=[
        "系统中不存在POST /system/user/batchDelete接口",
        "用户删除使用DELETE /system/user/{userIds}，通过路径参数传入多个ID实现批量删除",
        "前端user.js中也没有batchDelete函数"
    ],
    notes="Unanswerable: batchDelete endpoint doesn't exist. Tests uncertainty."
))

# 24. en, hard, unanswerable - dynamic URL trace that can't be verified
questions.append(q(
    seq=24, task_type="TRACE_CHAIN", lang="en", diff="hard",
    question="The frontend job module calls a function to get job details by ID using a dynamically constructed URL. Can you trace this specific frontend request through the REQUESTS_API relation in the static index to its backend handler?",
    answerable=False,
    eval_layers=["routing", "retrieval"],
    gold_entities=["GET /monitor/job/{jobId}", "SysJobController"],
    gold_nodes=[],
    gold_edges=[],
    gold_files=[
        "ruoyi-ui/src/api/monitor/job.js",
        "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java"
    ],
    required_claims=[],
    expected_uncertainties=[
        "The frontend getJob function constructs the URL dynamically: '/monitor/job/' + jobId",
        "The static index marks this as dynamic_url and does NOT store a REQUESTS_API relation for it",
        "While the backend endpoint GET /monitor/job/{jobId} exists in SysJobController, the trace cannot be verified through the index"
    ],
    source_files=["ruoyi-ui/src/api/monitor/job.js", "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java"],
    source_lines=["ruoyi-ui/src/api/monitor/job.js:13-18", "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java:70-75"],
    notes="Unanswerable trace: dynamic URL prevents index-based verification. Frontend request included."
))

# TRACE_CHAIN count check:
# zh = #13,15,17,19,21,23 = 6
# en = #14,16,18,20,22,24 = 6
# easy = #13,14 = 2
# medium = #15,16,17,18,19,20 = 6
# hard = #21,22,23,24 = 4
# answerable = #13,14,15,16,17,18,19,21,22 = 9
# unanswerable = #20,23,24 = 3
# Frontend requests: #13,14,17,18,19,20,21,22,24 = at least 4 ✓
# Controller->Service: #15,16,17,19 = at least 4 ✓
# HTTP method/path mismatch or unresolved: #20(unresolved /logout), #22(method mismatch), #24(dynamic URL unresolved) = at least 3 ✓


# ================================================================
# CHANGE_PLAN (12): zh=6, en=6
# easy=2, medium=5, hard=5
# answerable=9, unanswerable=3
# Since repo has only 1 commit, all are hypothetical changes
# ================================================================

# 25. zh, easy, answerable - add a simple endpoint
questions.append(q(
    seq=25, task_type="CHANGE_PLAN", lang="zh", diff="easy",
    question="如果需要在通知公告模块中新增一个\"置顶公告\"的功能，需要修改哪些文件？请列出后端控制器、服务接口、服务实现和前端API文件。",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysNoticeController", "ISysNoticeService", "SysNoticeServiceImpl"],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/ISysNoticeService.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysNoticeServiceImpl.java",
        "ruoyi-ui/src/api/system/notice.js",
        "ruoyi-system/src/main/java/com/ruoyi/system/domain/SysNotice.java"
    ],
    required_claims=[
        "需要修改SysNoticeController添加新的端点方法",
        "需要在ISysNoticeService接口中添加新方法声明",
        "需要在SysNoticeServiceImpl中实现新方法",
        "可能需要修改SysNotice实体类添加isTop字段",
        "需要在前端notice.js中添加对应的API调用函数"
    ],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/ISysNoticeService.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysNoticeServiceImpl.java"
    ],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java:32-150"],
    notes="Hypothetical change: add pin/top feature to notices."
))

# 26. en, easy, answerable - add export feature
questions.append(q(
    seq=26, task_type="CHANGE_PLAN", lang="en", diff="easy",
    question="If you needed to add an Excel export feature for the online user list (currently only GET /monitor/online/list exists), which files would need to be modified?",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysUserOnlineController", "ISysUserOnlineService"],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/SysUserOnlineController.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/ISysUserOnlineService.java",
        "ruoyi-ui/src/api/monitor/online.js"
    ],
    required_claims=[
        "SysUserOnlineController needs a new @PostMapping('/export') method",
        "The method would use ExcelUtil like other controllers do",
        "Frontend online.js needs a new export function",
        "The ISysUserOnlineService may not need changes if data is already available"
    ],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/SysUserOnlineController.java",
        "ruoyi-ui/src/api/monitor/online.js"
    ],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/SysUserOnlineController.java:41-70"],
    notes="Hypothetical change: add export to online users. Uses existing pattern from other controllers."
))

# 27. zh, medium, answerable - modify user registration
questions.append(q(
    seq=27, task_type="CHANGE_PLAN", lang="zh", diff="medium",
    question="如果要为用户注册功能添加邮箱验证步骤，需要修改哪些文件和类？请分析注册流程涉及的后端控制器、服务类和可能需要新增的组件。",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysRegisterController", "SysRegisterService", "POST /register"],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRegisterController.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/SysRegisterService.java",
        "ruoyi-ui/src/api/login.js"
    ],
    required_claims=[
        "需要修改SysRegisterController添加发送验证邮件的端点",
        "需要在SysRegisterService中添加邮件发送逻辑",
        "可能需要新增邮件服务工具类",
        "需要修改注册流程使其先发送验证码再完成注册",
        "前端login.js需要添加对应的API调用"
    ],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRegisterController.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/SysRegisterService.java"
    ],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRegisterController.java:28-37"],
    notes="Hypothetical change: add email verification to registration."
))

# 28. en, medium, answerable - add audit logging
questions.append(q(
    seq=28, task_type="CHANGE_PLAN", lang="en", diff="medium",
    question="To add audit logging for all cache modification operations (clear specific cache name, clear specific key, clear all), which files would need to be modified and what pattern should be followed?",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "CacheController",
        "DELETE /monitor/cache/clearCacheName/{cacheName}",
        "DELETE /monitor/cache/clearCacheKey/{cacheKey}",
        "DELETE /monitor/cache/clearCacheAll"
    ],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java"
    ],
    required_claims=[
        "CacheController has 3 DELETE endpoints for cache clearing",
        "The @Log annotation pattern from other controllers (like SysUserController) should be followed",
        "Each of the 3 clear methods needs a @Log annotation with appropriate BusinessType",
        "The existing controllers in system module already use this pattern"
    ],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java"
    ],
    source_lines=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/monitor/CacheController.java:97-121",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:68-76"
    ],
    notes="Hypothetical change: add @Log to cache operations. Pattern already exists in other controllers."
))

# 29. zh, medium, answerable - add new permission check
questions.append(q(
    seq=29, task_type="CHANGE_PLAN", lang="zh", diff="medium",
    question="如果要给公告模块的\"标记已读\"和\"批量标记已读\"接口添加权限控制注解，应该修改哪个文件的哪些方法？参考系统中其他接口的权限命名规范，应该使用什么权限字符串？",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "SysNoticeController",
        "POST /system/notice/markRead",
        "POST /system/notice/markReadAll"
    ],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java"
    ],
    required_claims=[
        "markRead和markReadAll方法当前没有@PreAuthorize注解",
        "应参考同控制器中其他方法使用的权限格式：system:notice:xxx",
        "例如可以添加@PreAuthorize(\"@ss.hasPermi('system:notice:edit')\")",
        "需要修改SysNoticeController中对应方法"
    ],
    source_files=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java"],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java:104-124"],
    notes="Hypothetical change: add permission annotations to existing methods that lack them."
))

# 30. en, medium, answerable - refactor split controller
questions.append(q(
    seq=30, task_type="CHANGE_PLAN", lang="en", diff="medium",
    question="If you wanted to refactor the code generation module to separate the import/create table operations into a dedicated controller (leaving only query/edit/delete/generate in the existing one), which files and endpoints would be affected?",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "GenController",
        "POST /tool/gen/importTable",
        "POST /tool/gen/createTable",
        "IGenTableService",
        "IGenTableColumnService"
    ],
    gold_files=[
        "ruoyi-generator/src/main/java/com/ruoyi/generator/controller/GenController.java",
        "ruoyi-ui/src/api/tool/gen.js"
    ],
    required_claims=[
        "POST /tool/gen/importTable and POST /tool/gen/createTable would move to a new controller",
        "GenController currently injects both IGenTableService and IGenTableColumnService",
        "The new controller would need IGenTableService injection",
        "Frontend gen.js importTable and createTable functions would need URL updates if path prefix changes",
        "Permission annotations (tool:gen:import) would move to the new controller"
    ],
    source_files=["ruoyi-generator/src/main/java/com/ruoyi/generator/controller/GenController.java"],
    source_lines=["ruoyi-generator/src/main/java/com/ruoyi/generator/controller/GenController.java:113-160"],
    notes="Hypothetical change: split GenController."
))

# 31. zh, medium, unanswerable - vague requirement
questions.append(q(
    seq=31, task_type="CHANGE_PLAN", lang="zh", diff="medium",
    question="如果要优化系统的整体性能，应该从哪些方面入手？需要修改哪些核心文件？",
    answerable=False,
    eval_layers=["routing", "retrieval"],
    gold_entities=[],
    gold_files=[],
    required_claims=[],
    expected_uncertainties=[
        "\"整体性能优化\"范围过于宽泛，无法确定具体的修改文件",
        "可能的方向包括数据库查询优化、缓存策略、异步处理等，但无法从代码结构中确定优先级",
        "需要更具体的性能瓶颈描述才能给出精确的修改方案"
    ],
    notes="Unanswerable: too vague to determine specific files. Tests uncertainty expression."
))

# 32. en, hard, answerable - add WebSocket notification
questions.append(q(
    seq=32, task_type="CHANGE_PLAN", lang="en", diff="hard",
    question="To implement real-time WebSocket-based notification delivery for the notice module (so users get instant updates when new notices are published), what changes would be needed across the backend and frontend? Consider the existing notice architecture.",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "SysNoticeController",
        "SysNoticeServiceImpl",
        "ISysNoticeService",
        "SysNoticeReadServiceImpl"
    ],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysNoticeServiceImpl.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysNoticeReadServiceImpl.java",
        "ruoyi-ui/src/api/system/notice.js"
    ],
    required_claims=[
        "Backend: Need to add WebSocket configuration (Spring WebSocket)",
        "Backend: SysNoticeServiceImpl.insertNotice needs to publish WebSocket event after insert",
        "Backend: Need a new WebSocket handler/endpoint for notification delivery",
        "Backend: May need to modify SecurityConfig to permit WebSocket endpoint",
        "Frontend: Need WebSocket client connection logic",
        "Frontend: The existing listNoticeTop and markNoticeRead APIs would still be needed for initial load",
        "The existing ISysNoticeReadService already tracks read status per user"
    ],
    expected_uncertainties=["Exact WebSocket library choice and configuration details are implementation decisions"],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java"
    ],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysNoticeController.java:32-150"],
    notes="Hard hypothetical: cross-cutting change requiring new infrastructure."
))

# 33. zh, hard, answerable - migrate auth system
questions.append(q(
    seq=33, task_type="CHANGE_PLAN", lang="zh", diff="hard",
    question="如果需要将系统的JWT认证机制从Redis存储迁移到数据库存储（例如为了支持无Redis部署），需要修改哪些核心文件？请分析涉及认证、令牌管理和安全配置的所有相关文件。",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "TokenService",
        "JwtAuthenticationTokenFilter",
        "SecurityConfig",
        "LogoutSuccessHandlerImpl",
        "SysLoginService"
    ],
    gold_files=[
        "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/TokenService.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/filter/JwtAuthenticationTokenFilter.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/handle/LogoutSuccessHandlerImpl.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/SysLoginService.java"
    ],
    required_claims=[
        "TokenService是核心，它使用RedisCache存储令牌信息，需要改为数据库存储",
        "JwtAuthenticationTokenFilter在每次请求时从TokenService获取用户信息",
        "LogoutSuccessHandlerImpl删除Redis中的令牌缓存",
        "SysLoginService调用TokenService.createToken创建令牌",
        "SecurityConfig配置了JWT过滤器和登出处理",
        "可能需要新增数据库表和对应的Mapper"
    ],
    source_files=[
        "ruoyi-framework/src/main/java/com/ruoyi/framework/web/service/TokenService.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/filter/JwtAuthenticationTokenFilter.java",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java"
    ],
    source_lines=[
        "ruoyi-framework/src/main/java/com/ruoyi/framework/config/SecurityConfig.java:85-117",
        "ruoyi-framework/src/main/java/com/ruoyi/framework/security/filter/JwtAuthenticationTokenFilter.java:30-43"
    ],
    notes="Hard: cross-cutting architectural change affecting multiple framework files."
))

# 34. en, hard, unanswerable
questions.append(q(
    seq=34, task_type="CHANGE_PLAN", lang="en", diff="hard",
    question="If we wanted to migrate the entire RuoYi-Vue backend from Spring Boot to Quarkus framework, what would be the complete list of files that need to be rewritten?",
    answerable=False,
    eval_layers=["routing", "retrieval"],
    gold_entities=[],
    gold_files=[],
    required_claims=[],
    expected_uncertainties=[
        "A full framework migration would affect virtually all 266 Java files",
        "The scope is too large to enumerate precisely",
        "Spring-specific annotations (@RestController, @Autowired, @PreAuthorize) would all need Quarkus equivalents",
        "Spring Security configuration would need a complete replacement"
    ],
    notes="Unanswerable: scope too large for precise file listing."
))

# 35. zh, hard, answerable - add multi-tenancy
questions.append(q(
    seq=35, task_type="CHANGE_PLAN", lang="zh", diff="hard",
    question="如果要为系统添加多租户支持，使得不同租户的用户只能看到自己租户下的数据，现有的哪些核心模块需要修改？请分析用户、角色、部门、菜单四个模块的修改影响。",
    answerable=True,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=[
        "SysUserController",
        "SysRoleController",
        "SysDeptController",
        "SysMenuController",
        "SysUserServiceImpl",
        "SysRoleServiceImpl",
        "SysDeptServiceImpl",
        "SysMenuServiceImpl"
    ],
    gold_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysRoleController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysDeptController.java",
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysMenuController.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysRoleServiceImpl.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysDeptServiceImpl.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysMenuServiceImpl.java"
    ],
    required_claims=[
        "用户、角色、部门、菜单实体类都需要添加tenantId字段",
        "所有Service层的查询方法都需要增加租户过滤条件",
        "Controller层的权限校验可能需要增加租户隔离逻辑",
        "TokenService需要在LoginUser中存储租户信息",
        "数据库表结构需要修改",
        "数据范围校验(checkUserDataScope等)需要与租户隔离结合"
    ],
    expected_uncertainties=["具体的租户隔离策略(行级隔离、Schema隔离、数据库隔离)需要架构决策"],
    source_files=[
        "ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java",
        "ruoyi-system/src/main/java/com/ruoyi/system/service/impl/SysUserServiceImpl.java"
    ],
    source_lines=["ruoyi-admin/src/main/java/com/ruoyi/web/controller/system/SysUserController.java:59-66"],
    notes="Hard: architectural cross-cutting change. No exact file names in question."
))

# 36. en, hard, unanswerable
questions.append(q(
    seq=36, task_type="CHANGE_PLAN", lang="en", diff="hard",
    question="To fix the security vulnerability where scheduled jobs can execute arbitrary Java methods via the invoke target, what is the minimal set of code changes needed while still preserving the scheduling functionality?",
    answerable=False,
    eval_layers=["routing", "retrieval", "synthesis"],
    gold_entities=["SysJobController", "SysJobServiceImpl"],
    gold_files=[
        "ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java",
        "ruoyi-quartz/src/main/java/com/ruoyi/quartz/service/impl/SysJobServiceImpl.java"
    ],
    required_claims=[],
    expected_uncertainties=[
        "The exact 'minimal' change set depends on the chosen security strategy",
        "Options include: stricter whitelist, sandboxed execution, removing reflection-based invocation entirely",
        "The current whitelist in ScheduleUtils.whiteList provides some protection but the exact scope is hard to determine from static analysis alone",
        "Whether the fix should be in the controller validation, the service execution, or both is a design decision"
    ],
    source_files=["ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java"],
    source_lines=["ruoyi-quartz/src/main/java/com/ruoyi/quartz/controller/SysJobController.java:80-111"],
    notes="Unanswerable: 'minimal change' is subjective and the execution mechanism is in service layer not visible from controller alone."
))

# CHANGE_PLAN count check:
# zh = #25,27,29,31,33,35 = 6
# en = #26,28,30,32,34,36 = 6
# easy = #25,26 = 2
# medium = #27,28,29,30,31 = 5
# hard = #32,33,34,35,36 = 5
# answerable = #25,26,27,28,29,30,32,33,35 = 9
# unanswerable = #31,34,36 = 3

# ================================================================
# Final verification
# ================================================================

assert len(questions) == 36, f"Expected 36, got {len(questions)}"

type_counts = {}
lang_counts = {}
diff_counts = {}
ans_counts = {}

for qq in questions:
    type_counts[qq["task_type"]] = type_counts.get(qq["task_type"], 0) + 1
    lang_counts[qq["language"]] = lang_counts.get(qq["language"], 0) + 1
    diff_counts[qq["difficulty"]] = diff_counts.get(qq["difficulty"], 0) + 1
    ans_counts[qq["answerable"]] = ans_counts.get(qq["answerable"], 0) + 1

print(f"Task types: {type_counts}")
print(f"Languages: {lang_counts}")
print(f"Difficulty: {diff_counts}")
print(f"Answerable: {ans_counts}")

assert type_counts.get("CODE_QA", 0) == 12, f"CODE_QA={type_counts.get('CODE_QA',0)}"
assert type_counts.get("TRACE_CHAIN", 0) == 12, f"TRACE_CHAIN={type_counts.get('TRACE_CHAIN',0)}"
assert type_counts.get("CHANGE_PLAN", 0) == 12, f"CHANGE_PLAN={type_counts.get('CHANGE_PLAN',0)}"
assert lang_counts.get("zh", 0) == 18, f"zh={lang_counts.get('zh',0)}"
assert lang_counts.get("en", 0) == 18, f"en={lang_counts.get('en',0)}"
assert diff_counts.get("easy", 0) == 8, f"easy={diff_counts.get('easy',0)}"
assert diff_counts.get("medium", 0) == 16, f"medium={diff_counts.get('medium',0)}"
assert diff_counts.get("hard", 0) == 12, f"hard={diff_counts.get('hard',0)}"
assert ans_counts.get(True, 0) == 27, f"answerable={ans_counts.get(True,0)}"
assert ans_counts.get(False, 0) == 9, f"unanswerable={ans_counts.get(False,0)}"

# Verify special properties
no_exact_names = 0
distractor_entities = 0
same_name_entities = 0
dynamic_unprovable = 0
uncertainty_required = 0
trace_frontend = 0
trace_ctrl_svc = 0
http_mismatch = 0

for qq in questions:
    qtext = qq["question"]
    # No exact names: question doesn't contain class names, method names, or file paths
    # Simple heuristic: check for common patterns
    has_exact = any(kw in qtext for kw in [
        "Controller", "Service", "ServiceImpl", ".java", ".js", ".vue",
        "getInfo", "selectUserList", "insertNotice", "updateRole",
        "SysLoginController", "SysUserController", "SysRoleController",
        "SysDeptController", "SysMenuController", "SysNoticeController",
        "SysConfigController", "SysProfileController", "SysJobController",
        "GenController", "CacheController", "TokenService",
        "BaseController", "SysLoginService"
    ])
    if not has_exact:
        no_exact_names += 1

    if qq.get("expected_uncertainties"):
        uncertainty_required += 1

    if qq["task_type"] == "TRACE_CHAIN":
        # Check if frontend files are in source
        for sf in qq.get("source_files", []):
            if "ruoyi-ui" in sf:
                trace_frontend += 1
                break
        # Check for controller->service edges
        for edge in qq.get("gold_edges", []):
            if edge.get("type") == "CALLS_METHOD":
                trace_ctrl_svc += 1
                break
        # Check for HTTP mismatch/unresolved
        if not qq["answerable"] or "dynamic" in qtext.lower() or "mismatch" in qtext.lower():
            if any("dynamic" in str(u).lower() or "not handled" in str(u).lower() or "unmatched" in str(u).lower()
                   for u in qq.get("expected_uncertainties", [])):
                http_mismatch += 1

print(f"\nSpecial properties:")
print(f"No exact names: {no_exact_names} (need >=9)")
print(f"Uncertainty required: {uncertainty_required} (need >=4)")
print(f"Trace with frontend: {trace_frontend} (need >=4)")
print(f"Trace ctrl->svc: {trace_ctrl_svc} (need >=4)")
print(f"HTTP mismatch/unresolved: {http_mismatch} (need >=3)")

# Write JSONL
output_path = r"F:\LIUQINGYUN\ResearchCode_Agent\evaluation\annotations\proposed\pilot_candidates.jsonl"
with open(output_path, "w", encoding="utf-8") as f:
    for qq in questions:
        f.write(json.dumps(qq, ensure_ascii=False) + "\n")

print(f"\nWritten {len(questions)} questions to {output_path}")
