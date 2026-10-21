# Pattern Reborn Generation Hardening Implementation Plan

> 历史文档（2026-10-21 标记）：本文记录比赛阶段的设计或实施计划，不再定义当前产品范围。请以[产品化基线](../../product/README.md)为准。原始内容保留供追溯；数据完整性、来源与密钥保护要求继续有效。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Seedream/Qwen requests faithful, provider-isolated, diagnosable, and resistant to accidental duplicate paid calls.

**Architecture:** Keep provider-neutral requests in `generation/base.py`, adapter-specific payloads in provider modules, and transport behavior in `generation/http.py`. Give every generation a stable local operation ID and return typed uncertain outcomes rather than treating every transport problem as malformed input.

**Tech Stack:** Python 3.11, Pydantic 2, HTTPX, Pillow, respx, pytest

**Spec:** `docs/superpowers/specs/2026-08-30-pattern-reborn-hardening-ui-redesign.md`

## Global Constraints

- The visible provider/model selector remains available in platform-default and BYOK modes.
- BYOK credentials are provider-specific, memory-only, masked, and absent from serialization.
- Generation count remains exactly one.
- Redirects, result bytes, and decoded images remain bounded and safely validated.
- An ambiguous timeout cannot expose an indistinguishable one-click paid retry.
- Every production change starts with a failing regression test and ends with a focused commit.

---

### Task 1: Preserve negative constraints and exact dispatched prompt

**Files:**
- Modify: `src/pattern_reborn/generation/service.py`
- Modify: `src/pattern_reborn/generation/seedream.py`
- Modify: `src/pattern_reborn/generation/qwen.py`
- Modify: `tests/test_generation_service.py`
- Modify: `tests/test_seedream.py`
- Modify: `tests/test_qwen.py`

**Interfaces:**
- Produces: `compose_generation_prompt(request) -> str` containing a delimited negative-constraints segment; adapters store/return the exact composed prompt.
- Consumes: existing `GenerationRequest.negative_constraints`.

- [ ] **Step 1: Write failing adapter-fidelity tests**

```python
def test_composed_prompt_contains_negative_constraints(generation_request):
    request = generation_request.model_copy(update={"negative_constraints": "不要文字、不要水印"})
    prompt = compose_generation_prompt(request)
    assert "负面约束：不要文字、不要水印" in prompt

def test_seedream_payload_sends_exact_composed_prompt(respx_mock, adapter, request):
    adapter.generate(request, SecretStr("secret"))
    payload = json.loads(respx_mock.calls[0].request.content)
    assert payload["prompt"] == request.prompt
```

- [ ] **Step 2: Verify Seedream currently omits the constraints**

Run: `.venv\Scripts\python.exe -m pytest tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py -q`

Expected: FAIL on the negative-constraint assertion.

- [ ] **Step 3: Compose the constraint exactly once**

```python
if request.negative_constraints.strip():
    parts.append("负面约束：" + request.negative_constraints.strip())
line = "；".join(parts)
return request.prompt.rstrip() if line in request.prompt else f"{request.prompt.rstrip()}\n{line}"
```

Adapters use `request.prompt` verbatim after service composition; do not invent a second provider-specific paraphrase. Persist the composed prompt returned by the provider result.

- [ ] **Step 4: Run request-fidelity tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py tests/ui/test_generation_controls.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/generation/service.py src/pattern_reborn/generation/seedream.py src/pattern_reborn/generation/qwen.py tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py
git commit -m "fix: preserve generation constraints in provider prompts"
```

### Task 2: Distinguish network, provider, and uncertain failures

**Files:**
- Modify: `src/pattern_reborn/generation/base.py`
- Modify: `src/pattern_reborn/generation/http.py`
- Modify: `tests/test_generation_base.py`
- Modify: `tests/test_generation_service.py`
- Modify: `tests/test_seedream.py`
- Modify: `tests/test_qwen.py`

**Interfaces:**
- Produces: `FailureKind.NETWORK`, `FailureKind.PROVIDER`, `FailureKind.UNCERTAIN`; `GenerationFailure.retry_safe: bool`.
- Consumes: existing redacted error-code machinery.

- [ ] **Step 1: Write failing failure-classification tests**

```python
def test_dns_failure_maps_to_network(respx_mock, adapter, request):
    respx_mock.post(URL).mock(side_effect=httpx.ConnectError("dns"))
    with pytest.raises(GenerationFailure) as caught:
        adapter.generate(request, SecretStr("key"))
    assert caught.value.kind is FailureKind.NETWORK
    assert caught.value.retry_safe is True

def test_provider_500_is_not_reported_as_invalid_request():
    assert classify_http_error(500, "internal") is FailureKind.PROVIDER
```

- [ ] **Step 2: Verify current mappings collapse these cases to malformed**

Run: `.venv\Scripts\python.exe -m pytest tests/test_generation_base.py tests/test_seedream.py tests/test_qwen.py -q`

Expected: FAIL.

- [ ] **Step 3: Add typed failure semantics and Chinese recovery copy**

```python
class FailureKind(str, Enum):
    AUTH = "auth"
    QUOTA = "quota"
    MODERATION = "moderation"
    TIMEOUT = "timeout"
    MALFORMED = "malformed"
    MISSING_CREDENTIAL = "missing_credential"
    NETWORK = "network"
    PROVIDER = "provider"
    UNCERTAIN = "uncertain"

USER_MESSAGE_ZH[FailureKind.NETWORK] = "网络连接失败，请检查连接后重试。"
USER_MESSAGE_ZH[FailureKind.PROVIDER] = "生成服务暂时异常，请稍后重试。"
USER_MESSAGE_ZH[FailureKind.UNCERTAIN] = "请求结果状态不确定，可能已经产生费用，请先核对后再发起新请求。"
```

Map connect/DNS errors to `NETWORK`, HTTP 500–599 to `PROVIDER`, and a read timeout after request dispatch to `UNCERTAIN` with `retry_safe=False`.

- [ ] **Step 4: Run provider and service tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_generation_base.py tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py -q`

Expected: PASS and no secret appears in exception text.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/generation/base.py src/pattern_reborn/generation/http.py tests/test_generation_base.py tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py
git commit -m "fix: classify generation transport failures"
```

### Task 3: Follow bounded image redirects and cap response bytes

**Files:**
- Modify: `src/pattern_reborn/generation/http.py`
- Modify: `src/pattern_reborn/generation/service.py`
- Modify: `tests/test_seedream.py`
- Modify: `tests/test_qwen.py`
- Modify: `tests/test_generation_service.py`

**Interfaces:**
- Produces: `download_bytes(client, url, *, max_redirects=3, max_bytes=20_000_000) -> bytes`.
- Consumes: safe image decoding and typed failures.

- [ ] **Step 1: Write failing redirect, loop, and oversized-result tests**

```python
def test_result_download_follows_one_temporary_redirect(respx_mock, client):
    respx_mock.get("https://a/result").mock(return_value=httpx.Response(302, headers={"location": "https://cdn/image.png"}))
    respx_mock.get("https://cdn/image.png").mock(return_value=httpx.Response(200, headers={"content-type": "image/png"}, content=PNG))
    assert download_bytes(client, "https://a/result") == PNG

def test_result_download_rejects_redirect_loop(respx_mock, client):
    respx_mock.get("https://a/loop").mock(
        return_value=httpx.Response(302, headers={"location": "https://b/loop"})
    )
    respx_mock.get("https://b/loop").mock(
        return_value=httpx.Response(302, headers={"location": "https://a/loop"})
    )
    with pytest.raises(GenerationFailure) as caught:
        download_bytes(client, "https://a/loop")
    assert caught.value.kind is FailureKind.MALFORMED
```

- [ ] **Step 2: Verify 302 is currently treated as successful body bytes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_seedream.py tests/test_qwen.py tests/test_generation_service.py -q`

Expected: FAIL.

- [ ] **Step 3: Implement explicit bounded redirects and streamed byte limit**

```python
for hop in range(max_redirects + 1):
    with client.stream("GET", current_url, timeout=60.0) as response:
        if response.is_redirect:
            if hop == max_redirects or "location" not in response.headers:
                raise_mapped(FailureKind.MALFORMED)
            current_url = str(response.url.join(response.headers["location"]))
            continue
        if response.status_code >= 400:
            raise_mapped(classify_http_error(response.status_code, response.text), str(response.status_code))
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > max_bytes:
                raise_mapped(FailureKind.MALFORMED)
        return bytes(data)
```

Only allow `http`/`https`; retain content-type and safe-decode validation after redirects.

- [ ] **Step 4: Run transport and provider tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/generation/http.py src/pattern_reborn/generation/service.py tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py
git commit -m "fix: bound redirected generation downloads"
```

### Task 4: Add stable operation IDs and provider idempotency hints

**Files:**
- Modify: `src/pattern_reborn/generation/base.py`
- Modify: `src/pattern_reborn/generation/seedream.py`
- Modify: `src/pattern_reborn/generation/qwen.py`
- Modify: `src/pattern_reborn/workflow.py`
- Modify: `tests/test_generation_base.py`
- Modify: `tests/test_seedream.py`
- Modify: `tests/test_qwen.py`
- Modify: `tests/test_workflow.py`

**Interfaces:**
- Produces: `GenerationRequest.operation_id: str`; outbound `X-Idempotency-Key`/provider-supported request field; uncertain persisted generation status.
- Consumes: lifecycle model from provenance plan and failure kinds from Task 2.

- [ ] **Step 1: Write failing operation-ID and uncertain-state tests**

```python
def test_same_confirmed_operation_uses_same_idempotency_key(adapter, request, respx_mock):
    request = request.model_copy(update={"operation_id": "op-0123456789abcdef"})
    adapter.generate(request, SecretStr("key"))
    assert respx_mock.calls[0].request.headers["X-Idempotency-Key"] == request.operation_id

def test_uncertain_timeout_is_persisted_not_confirmed(app_service):
    with pytest.raises(GenerationFailure):
        app_service.generate(PROJECT_ID, REQUEST, CredentialMode.PLATFORM, None)
    project = app_service.load_project(PROJECT_ID)
    assert project.generations[-1].status is GenerationStatus.UNCERTAIN
    assert project.artifacts.generation == []
```

- [ ] **Step 2: Verify current requests have no operation identity**

Run: `.venv\Scripts\python.exe -m pytest tests/test_generation_base.py tests/test_seedream.py tests/test_qwen.py tests/test_workflow.py -q`

Expected: FAIL.

- [ ] **Step 3: Generate once at confirmation and propagate unchanged**

```python
operation_id = f"op-{uuid4().hex}"
request = request.model_copy(update={"operation_id": operation_id})

headers = authorization_headers(credential)
headers["X-Idempotency-Key"] = request.operation_id
```

If provider documentation exposes a body idempotency field, use it in addition to the stable header. Do not regenerate the ID inside an adapter. On `FailureKind.UNCERTAIN`, persist a metadata-only uncertain record with no current artifact.

- [ ] **Step 4: Run generation and workflow tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_generation_base.py tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py tests/test_workflow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/pattern_reborn/generation/base.py src/pattern_reborn/generation/seedream.py src/pattern_reborn/generation/qwen.py src/pattern_reborn/workflow.py tests/test_generation_base.py tests/test_seedream.py tests/test_qwen.py tests/test_workflow.py
git commit -m "feat: track idempotent generation operations"
```

### Task 5: Generation checkpoint

**Files:**
- Modify only if verification exposes a regression in files changed by this plan.

**Interfaces:**
- Produces: stable provider contracts for the UI redesign plan.
- Consumes: Tasks 1–4 and schema-v2 generation lifecycle.

- [ ] **Step 1: Run every generation-focused test**

Run: `.venv\Scripts\python.exe -m pytest tests/test_generation_base.py tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py tests/test_config.py tests/ui/test_generation_controls.py tests/test_workflow.py -q`

Expected: PASS.

- [ ] **Step 2: Verify secrets do not appear in test output or tracked files**

Run: `git grep -n -I -E "(sk-[A-Za-z0-9]{8,}|Authorization: Bearer [^[]|api[_-]?key[=:][^$])" -- . ':!docs/superpowers/plans/*'`

Expected: no real or test-like secret value outside explicit redaction tests.

- [ ] **Step 3: Compile provider modules**

Run: `.venv\Scripts\python.exe -m compileall -q src\pattern_reborn\generation src\pattern_reborn\workflow.py`

Expected: exit code 0.

- [ ] **Step 4: Commit only checkpoint repairs**

```powershell
git add src/pattern_reborn/generation src/pattern_reborn/workflow.py tests/test_generation_base.py tests/test_generation_service.py tests/test_seedream.py tests/test_qwen.py tests/test_workflow.py tests/ui/test_generation_controls.py
git commit -m "test: close generation hardening regressions"
```
