# CALLS_METHOD Gap Analysis Report

**Project**: ResearchCode-Agent

**Target repository**: RuoYi-Vue

**Date**: 2026-07-15T16:19:17+08:00
**Diagnostic script**: `evaluation/scripts/diagnose_calls_method.py`

---

## 1. Executive Summary

The scanner produces **ZERO** `CALLS_METHOD` relations despite extracting **523 method
invocations** across **353 methods** in **266 Java files**. The root cause is a
**type-name mismatch** between the parser and the relation builder:

- The **parser** correctly extracts invocations with `receiver_type` set to the
  **declared field type** (e.g., `ISysUserService`, the interface).
- The **relation builder** only indexes methods from classes annotated with
  `@Service` and looks them up by the **implementation class name**
  (e.g., `SysUserServiceImpl`).
- No mapping exists between interface names and implementation class names,
  so **every service-related invocation** (217 interface-typed + 17 @Component-typed,
  totaling ~234 or 44.7% of all invocations) fails resolution.
- The remaining ~289 invocations (55.3%) target mapper interfaces, framework
  types (Redis, etc.), and other non-project-service receivers. These are
  **correctly outside the current graph model boundary** and are not affected
  by this bug.

This is not a case of missing data -- the parser does excellent work extracting
invocation metadata. The gap is entirely in the resolution layer, and only
affects the ~234 service-related invocations that should produce CALLS_METHOD
edges.

---

## 2. Root Cause Analysis

### 2.1 Primary cause: Interface-to-implementation type mismatch

**Where it happens**: `relation_builder.py`, lines 117-132

```
receiver_type = invocation.get("receiver_type")   # e.g., "ISysUserService"
...
candidates = [
    method
    for class_name in service_aliases.get(receiver_type, set())  # EMPTY
    ...
]
```

The `service_aliases` dictionary is built from classes with `is_service=True`
(line 63-74). It only contains implementation class names like
`SysUserServiceImpl`. When the receiver type is `ISysUserService` (the
interface), the lookup returns an empty set.

**Why the receiver type is the interface**: In `java_parser.py`,
`_injected_dependencies()` (lines 206-229) reads the field declaration type:

```java
@Autowired
private ISysUserService userService;  // Type is "ISysUserService" (the interface)
```

The parser records `dependencies["userService"] = "ISysUserService"`, which
becomes the `receiver_type` in every invocation.

**Why the implementation class name differs**: RuoYi-Vue follows the standard
Spring convention: controllers inject services by their **interface type**
(`ISysUserService`), while the **implementation class** (`SysUserServiceImpl`)
carries the `@Service` annotation. The parser indexes `SysUserServiceImpl`
because it visits `class_declaration` nodes and finds `@Service` on it.
Interfaces are `interface_declaration` nodes in tree-sitter and are never
visited at all.

### 2.2 Secondary cause: @Component not recognized as service

**Where it happens**: `java_parser.py`, line 104

```python
"is_service": "Service" in annotation_names,
```

Some service-like classes in RuoYi-Vue use `@Component` instead of `@Service`:

| Class                 | Annotation  | In service_classes? |
|-----------------------|-------------|---------------------|
| TokenService          | @Component  | No                  |
| SysPermissionService  | @Component  | No                  |
| SysPasswordService    | @Component  | No                  |
| SysLoginService       | @Component  | No                  |
| SysRegisterService    | @Component  | No                  |

This affects 17 invocations (3.3% of total) where these classes are the
receiver type.

### 2.3 Non-issue: Invocation extraction works correctly

The parser's `_service_invocations()` method (lines 274-302) correctly:

1. Walks all descendant AST nodes looking for `method_invocation`
2. Extracts the `object` node (receiver variable name)
3. Looks up the receiver in the `dependencies` map (from `@Autowired`/`@Resource` fields)
4. Records `{qualifier, method, receiver_type}`

For `SysUserController.java` alone, the parser extracts **35 invocations**
across **12 of 13 methods** -- all with correct receiver types.

---

## 3. Statistics

### 3.1 Pipeline overview

| Stage                                     | Count  |
|-------------------------------------------|--------|
| Java files parsed                         | 266    |
| Total entities extracted                  | 2,119  |
| Total parser relations (CONTAINS+API)     | 1,901  |
| Methods with invocation metadata          | 353    |
| Total invocations extracted               | 523    |
| Invocations with receiver_type            | 523 (100%) |
| Receiver types matching service_aliases   | 0 (0%) |
| CALLS_METHOD relations produced           | 0      |

### 3.2 Receiver type categories

| Category                           | Invocations | % of total | Graph model status                 |
|------------------------------------|-------------|------------|------------------------------------|
| Service interfaces (I*Service)     | ~217        | 41.5%      | **Affected by bug** -- interface-to-impl map missing |
| @Component classes                 | ~17         | 3.3%       | **Affected by bug** -- @Component not recognized |
| Mapper interfaces (*Mapper)        | ~180        | 34.4%      | Correctly outside graph model boundary |
| Framework types (Redis*, etc.)     | ~85         | 16.3%      | Correctly outside graph model boundary |
| Other (Class<T>, Producer, etc.)   | ~24         | 4.6%       | Correctly outside graph model boundary |

### 3.3 Top 10 unresolved receiver types

| Receiver type        | Count | Category          |
|----------------------|-------|-------------------|
| ISysUserService      | 40    | Service interface |
| ISysRoleService      | 30    | Service interface |
| RedisCache           | 28    | Framework         |
| ISysDeptService      | 22    | Service interface |
| SysUserMapper        | 22    | Mapper            |
| ISysMenuService      | 21    | Service interface |
| ISysConfigService    | 19    | Service interface |
| RedisTemplate        | 19    | Framework         |
| IGenTableService     | 17    | Service interface |
| SysDeptMapper        | 17    | Mapper            |

---

## 4. Ten Sample Traces

Each trace shows a real call from the RuoYi-Vue source code and how data flows
through the pipeline.

### Trace 1: SysUserController.list -> userService.selectUserList

| Step               | Value                                            |
|--------------------|--------------------------------------------------|
| Source file        | `SysUserController.java:64`                      |
| Source expression  | `userService.selectUserList(user)`               |
| Field declaration  | `@Autowired private ISysUserService userService` |
| Parser dependency  | `{"userService": "ISysUserService"}`             |
| Invocation metadata| `{"qualifier":"userService","method":"selectUserList","receiver_type":"ISysUserService"}` |
| Target impl class  | `SysUserServiceImpl` (has `@Service`)            |
| service_aliases lookup | `service_aliases.get("ISysUserService")` -> `{}` (MISS) |
| Resolution result  | **FAILED** -- receiver type not in aliases       |

### Trace 2: SysUserController.getInfo -> postService.selectPostAll

| Step               | Value                                            |
|--------------------|--------------------------------------------------|
| Source file        | `SysUserController.java:115`                     |
| Source expression  | `postService.selectPostAll()`                    |
| Field declaration  | `@Autowired private ISysPostService postService` |
| Invocation metadata| `{"qualifier":"postService","method":"selectPostAll","receiver_type":"ISysPostService"}` |
| Target impl class  | `SysPostServiceImpl` (has `@Service`)            |
| service_aliases lookup | `service_aliases.get("ISysPostService")` -> `{}` (MISS) |
| Resolution result  | **FAILED** -- receiver type not in aliases       |

### Trace 3: SysRoleController.edit -> tokenService.refreshPermissionByRoleId

| Step               | Value                                            |
|--------------------|--------------------------------------------------|
| Source file        | `SysRoleController.java:130`                     |
| Source expression  | `tokenService.refreshPermissionByRoleId(role.getRoleId(), permissionService)` |
| Field declaration  | `@Autowired private TokenService tokenService`   |
| Invocation metadata| `{"qualifier":"tokenService","method":"refreshPermissionByRoleId","receiver_type":"TokenService"}` |
| Target class       | `TokenService` (has `@Component`, NOT `@Service`) |
| In service_classes?| No -- `@Component` not recognized               |
| service_aliases lookup | `service_aliases.get("TokenService")` -> `{}` (MISS) |
| Resolution result  | **FAILED** -- @Component class not indexed as service |

### Trace 4: SysDeptController.list -> deptService.selectDeptList

| Step               | Value                                            |
|--------------------|--------------------------------------------------|
| Source file        | `SysDeptController.java:45`                      |
| Source expression  | `deptService.selectDeptList(dept)`               |
| Field declaration  | `@Autowired private ISysDeptService deptService` |
| Invocation metadata| `{"qualifier":"deptService","method":"selectDeptList","receiver_type":"ISysDeptService"}` |
| Target impl class  | `SysDeptServiceImpl` (has `@Service`)            |
| service_aliases lookup | `service_aliases.get("ISysDeptService")` -> `{}` (MISS) |
| Resolution result  | **FAILED** -- receiver type not in aliases       |

### Trace 5: SysMenuController.add -> menuService.insertMenu

| Step               | Value                                            |
|--------------------|--------------------------------------------------|
| Source file        | `SysMenuController.java:102`                     |
| Source expression  | `menuService.insertMenu(menu)`                   |
| Field declaration  | `@Autowired private ISysMenuService menuService` |
| Invocation metadata| `{"qualifier":"menuService","method":"insertMenu","receiver_type":"ISysMenuService"}` |
| Target impl class  | `SysMenuServiceImpl` (has `@Service`)            |
| service_aliases lookup | `service_aliases.get("ISysMenuService")` -> `{}` (MISS) |
| Resolution result  | **FAILED** -- receiver type not in aliases       |

### Trace 6: SysUserController.add -> deptService.checkDeptDataScope

| Step               | Value                                            |
|--------------------|--------------------------------------------------|
| Source file        | `SysUserController.java:127`                     |
| Source expression  | `deptService.checkDeptDataScope(user.getDeptId())` |
| Field declaration  | `@Autowired private ISysDeptService deptService` |
| Invocation metadata| `{"qualifier":"deptService","method":"checkDeptDataScope","receiver_type":"ISysDeptService"}` |
| Target impl class  | `SysDeptServiceImpl` (has `@Service`)            |
| service_aliases lookup | `service_aliases.get("ISysDeptService")` -> `{}` (MISS) |
| Resolution result  | **FAILED** -- receiver type not in aliases       |

### Trace 7: SysUserController.edit -> userService.updateUser

| Step               | Value                                            |
|--------------------|--------------------------------------------------|
| Source file        | `SysUserController.java:171`                     |
| Source expression  | `userService.updateUser(user)`                   |
| Field declaration  | `@Autowired private ISysUserService userService` |
| Invocation metadata| `{"qualifier":"userService","method":"updateUser","receiver_type":"ISysUserService"}` |
| Target impl class  | `SysUserServiceImpl` (has `@Service`)            |
| service_aliases lookup | `service_aliases.get("ISysUserService")` -> `{}` (MISS) |
| Resolution result  | **FAILED** -- receiver type not in aliases       |

### Trace 8: SysRoleController.edit -> permissionService (passed as argument)

This call passes `permissionService` as an argument to
`tokenService.refreshPermissionByRoleId(...)`. The parser captures the call to
`tokenService.refreshPermissionByRoleId()` but does NOT capture an invocation
for `permissionService` itself because it is not the receiver of a method call
in this expression. This is correct parser behavior.

### Trace 9: SysUserController.remove -> userService.deleteUserByIds

| Step               | Value                                            |
|--------------------|--------------------------------------------------|
| Source file        | `SysUserController.java:186`                     |
| Source expression  | `userService.deleteUserByIds(userIds)`           |
| Field declaration  | `@Autowired private ISysUserService userService` |
| Invocation metadata| `{"qualifier":"userService","method":"deleteUserByIds","receiver_type":"ISysUserService"}` |
| Target impl class  | `SysUserServiceImpl` (has `@Service`)            |
| service_aliases lookup | `service_aliases.get("ISysUserService")` -> `{}` (MISS) |
| Resolution result  | **FAILED** -- receiver type not in aliases       |

### Trace 10: SysRoleController.deptTree -> deptService.selectDeptListByRoleId

| Step               | Value                                            |
|--------------------|--------------------------------------------------|
| Source file        | `SysRoleController.java:250`                     |
| Source expression  | `deptService.selectDeptListByRoleId(roleId)`     |
| Field declaration  | `@Autowired private ISysDeptService deptService` |
| Invocation metadata| `{"qualifier":"deptService","method":"selectDeptListByRoleId","receiver_type":"ISysDeptService"}` |
| Target impl class  | `SysDeptServiceImpl` (has `@Service`)            |
| service_aliases lookup | `service_aliases.get("ISysDeptService")` -> `{}` (MISS) |
| Resolution result  | **FAILED** -- receiver type not in aliases       |

---

## 5. Issue Classification

The issue is **option (e): a combination**, with the following breakdown:

| Issue                                             | Impact    |
|---------------------------------------------------|-----------|
| **(b) Parser extracts invocations but receiver type is interface name** | Primary   |
| **(c) Relation builder rejects due to type mismatch (not ambiguity)**  | Primary   |
| **@Component not recognized as service**          | Secondary |
| Parser doesn't extract invocations at all         | NOT an issue |
| Relation builder rejects due to ambiguity         | NOT an issue |
| Relation builder rejects due to missing type      | NOT an issue (all 523 have receiver_type) |

The parser extraction is fully functional. The breakdown occurs at the
**resolution stage** in `_append_method_calls()`, where the interface name from
the invocation metadata cannot be matched to any entry in `service_aliases`.

**Important**: When `receiver_type` exists but does not match any key in
`service_aliases`, the relation builder does **NOT** fall through to
unique-name matching or any other heuristic. The invocation is silently
skipped. This means the 217 service interface calls and 17 @Component calls
are definitively lost -- they are not recovered by any fallback path.

---

## 6. Source Truth vs. Indexed Observation

For each sample, the "source truth" is what a human reading the code would
expect as a `CALLS_METHOD` edge, and the "indexed observation" is what the
scanner actually produces.

| Source call                                      | Expected edge                                  | Actually indexed |
|--------------------------------------------------|------------------------------------------------|------------------|
| SysUserController.list -> userService.selectUserList | SysUserController.list -> SysUserServiceImpl.selectUserList | NONE |
| SysUserController.getInfo -> postService.selectPostAll | SysUserController.getInfo -> SysPostServiceImpl.selectPostAll | NONE |
| SysUserController.getInfo -> roleService.selectRoleAll | SysUserController.getInfo -> SysRoleServiceImpl.selectRoleAll | NONE |
| SysUserController.add -> deptService.checkDeptDataScope | SysUserController.add -> SysDeptServiceImpl.checkDeptDataScope | NONE |
| SysUserController.edit -> userService.updateUser | SysUserController.edit -> SysUserServiceImpl.updateUser | NONE |
| SysUserController.remove -> userService.deleteUserByIds | SysUserController.remove -> SysUserServiceImpl.deleteUserByIds | NONE |
| SysRoleController.edit -> tokenService.refreshPermissionByRoleId | SysRoleController.edit -> TokenService.refreshPermissionByRoleId | NONE |
| SysRoleController.deptTree -> deptService.selectDeptListByRoleId | SysRoleController.deptTree -> SysDeptServiceImpl.selectDeptListByRoleId | NONE |
| SysDeptController.add -> deptService.insertDept  | SysDeptController.add -> SysDeptServiceImpl.insertDept | NONE |
| SysMenuController.add -> menuService.insertMenu  | SysMenuController.add -> SysMenuServiceImpl.insertMenu | NONE |

---

## 7. Recommendations

**Do NOT modify product code based on this report.** These are recommendations
for future implementation.

### 7.1 Primary fix: Interface-to-implementation mapping

The relation builder needs to resolve interface types to their implementations.
Two approaches:

**Approach A: Parse Java interfaces and track `implements` clauses**

- Extend the parser to visit `interface_declaration` nodes in addition to
  `class_declaration` nodes.
- For each `class_declaration`, parse the `super_interfaces` field to record
  which interfaces it implements.
- In the relation builder, when building `service_aliases`, also add the
  interface names as alias keys pointing to the implementing class.

This is the most correct approach but requires more parser work.

**Approach B: Name-convention heuristic**

- RuoYi-Vue follows a consistent naming convention: `I<Name>Service` (interface)
  maps to `<Name>ServiceImpl` (implementation).
- In `_append_method_calls()`, when the receiver type starts with `I` and ends
  with `Service`, try looking up the corresponding `*Impl` class.

This is simpler but fragile -- it breaks on codebases that don't follow this
convention.

**Approach C: Use `implements` data at the class level (hybrid)**

- When visiting a `class_declaration`, extract the `implements` clause text and
  store it in the class entity metadata.
- In the relation builder, build a reverse map: interface name -> set of
  implementing class names.
- Add interface names to `service_aliases` pointing to their implementations.

This is a good balance of correctness and implementation effort.

### 7.2 Secondary fix: Recognize @Component

Add `"Component"` to the service-detection check in `java_parser.py` line 104:

```python
"is_service": "Service" in annotation_names or "Component" in annotation_names,
```

This would recover 17 additional invocations (TokenService,
SysPermissionService, etc.).

### 7.3 Potential additional improvements

- **Filter out non-service receiver types**: Mappers, Redis, and framework types
  account for 55% of invocations. The parser could skip invocations where the
  receiver type is clearly not a project service (e.g., types containing
  "Mapper", "Redis", "Template", or generic type parameters).
- **Track constructor injection**: The parser already handles constructor-based
  dependency injection via `_constructor_dependencies()`. This is correct.
- **Handle `@Qualifier` and `@Named`**: Some codebases use explicit qualifier
  annotations to disambiguate. Not needed for RuoYi-Vue but relevant for
  larger projects.

### 7.4 Expected impact

If the primary fix (interface-to-impl mapping) and secondary fix (@Component
recognition) were both implemented:

- ~217 invocations would resolve via interface type matching
- ~17 invocations would resolve via @Component recognition
- ~289 invocations (mappers, framework, etc.) would still correctly be skipped,
  as they are outside the current graph model boundary
- **Estimated** CALLS_METHOD relations: **~200-230** (after deduplication and
  uniqueness checks)

> **Note**: The "~200-230" figure is an **estimate** based on the invocation
> counts and expected deduplication. It has not been verified by running the
> fixed pipeline. The actual count may differ depending on how many invocations
> resolve to the same target method and how deduplication is applied.

---

## 8. Files Referenced

| File | Purpose |
|------|---------|
| `backend/app/parsers/java_parser.py` | Java parser -- extracts invocations (lines 274-302) and dependency injection (lines 206-272) |
| `backend/app/parsers/relation_builder.py` | Relation builder -- `_append_method_calls()` (lines 58-155) |
| `backend/app/parsers/base.py` | Data types: `EntityCandidate`, `RelationCandidate`, `ParseResult` |
| `backend/app/services/index_service.py` | Orchestrates parsing and relation building (line 91: `build_relations()`) |
| `evaluation/scripts/diagnose_calls_method.py` | Diagnostic script created for this analysis |

---

## 9. Reproduction

Run the diagnostic script:

```powershell
.\.venv\python.exe ..\evaluation\scripts\diagnose_calls_method.py
```

The script parses all 266 Java files in RuoYi-Vue, extracts all invocations,
and traces each one through the relation builder's resolution logic, printing
detailed statistics and the exact failure reason for each invocation.
