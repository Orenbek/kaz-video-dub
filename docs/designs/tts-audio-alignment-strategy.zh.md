# 音频时长对齐完整策略方案（供 review）

## 1. 目标与边界

本文档描述 Kazakh dubbing pipeline 中，TTS 之后的**完整音频时长对齐策略**。目标不是做逐帧强对齐，而是在保证自然度优先的前提下，让每个 segment 的最终音频尽量贴近原始时间窗，并且在最终 compose 时保持 timeline-safe。

### 核心目标
- 让每个 segment 的最终音频尽量接近 `target_duration`
- 优先保持语音自然度，避免激进 DSP
- 避免在 final compose 时与下一个 segment 发生不可接受的碰撞
- 把每一步决策显式记录到 metadata / artifacts 中，便于调试
- 保持职责清晰：translation 负责文本长度控制；TTS 对齐层负责测量、判断、有限修正、持久化

### 明确边界
- **不在 TTS 阶段做 post-translation text rewrite**
- **文本侧长度控制只能发生在 translation prompt 阶段**
- **不引入 duration bucket 逻辑**
- **不会有裁剪 voiced content**
- 当前策略仅覆盖单 segment 局部决策，不做跨多个 segment 的全局优化

---

## 2. 总体策略概览

完整策略建议分为四层：

1. **Translation length shaping**  
   在翻译 prompt 中提前约束：源文与哈语长度大致相当、避免不必要扩写、短句保持简洁、适合 dubbing 口播。

2. **Initial TTS generation**  
   先按翻译结果做一次原始 TTS，得到原始音频结果。

3. **Duration evaluation and bounded correction**  
   先看是否与下一个 segment 发生 collision，再结合 target / actual / ratio / error，判断是否需要进入 bounded time-stretch。

4. **Timeline-safe compose preparation**  
   在 compose 前做局部时间线安全处理：
   - 提前结束：允许补静音
   - 轻微 overhang：在允许范围内保留
   - 明显撞下一个 segment：优先尝试移除 trailing silence；若仍不安全则标记 `manual_review`

一句话总结：

> translation 负责“尽量别写太长”，TTS alignment 负责“先看 collision，再看时长是否要修；能小修就修，不能小修就显式暴露问题”。

---

## 3. 每个 segment 的完整处理流程

### 3.1 输入
每个 segment 的已知输入：
- `id`
- `start`
- `end`
- `text_en`
- `text_kk`
- 下一个 segment 的 `start`（若存在）
- alignment config

### 3.2 关键派生量
- `target_duration = end - start`
- `initial_tts_duration = raw wav duration`
- `duration_ratio = actual / target`
- `duration_error_seconds = actual - target`
- `next_safe_end = next_segment.start + allow_minor_overhang_seconds`（若有下一个 segment）
- `max_safe_duration = next_safe_end - segment.start`（若有下一个 segment）
- `has_timeline_collision = actual_duration > max_safe_duration`（若有下一个 segment）

### 3.3 建议的状态分层
建议保留这几个最终状态：
- `preferred`
- `acceptable`
- `too_short`
- `too_long`
- `manual_review`

说明：
- `preferred`：时长误差很小，且没有不可接受的 timeline collision
- `acceptable`：时长虽然不是最优，但仍在容忍范围内，且没有不可接受的 timeline collision
- `too_short`：偏短，未进入或未完成有效修正，但仍可继续管线
- `too_long`：偏长，未进入或未完成有效修正，但仍可继续管线
- `manual_review`：严重失配、严重 collision、或经过允许的修正后仍不安全

这里不再单独引入 `corrected` 状态。
是否做过 stretch、pad silence、trim trailing silence，统一通过 `correction_actions` 记录。

这样状态含义更清晰：
- `duration_status` 表示**最终结果现在是什么状态**
- `correction_actions` 表示**为达到当前状态做过什么处理**

---

## 4. 决策流程（状态机式收敛版）

这一版按讨论结果做进一步收敛：
- **先看 collision，再决定是否必须 correction**
- **有 collision 时，优先判断能否通过有限压缩解除 collision**
- **没 collision 时，acceptable 默认直接接受，不再为了追指标继续 stretch**
- **too_short / too_long 只尝试 bounded stretch，不做文本 rewrite，不做 voiced trim**
- **manual_review 不阻断主 pipeline，而是额外产出 repair artifact，后续走单独 repair script**

### Step 0：translation 阶段（前置约束）
translation prompt 必须明确要求：
- 保持语义
- 口语化、适合配音
- 源文与译文长度大致相当
- 避免不必要扩写
- 短 segment 保持紧凑

这一层不保证最终时长，但负责降低极端 long tail mismatch 的概率。

### Step 1：生成 raw TTS
对每个 segment：
- 直接用 `text_kk` 调 TTS provider
- 写入 `artifacts/tts_raw/<segment_id>.wav`（建议完整策略实现时引入）
- 测量 raw 音频时长

记录：
- `target_duration`
- `initial_tts_duration`
- `tts_duration`（先等于 raw）
- `duration_error_seconds`
- `correction_actions=[]`
- `time_stretch_ratio=None`

### Step 2：先判断是否存在 collision
raw TTS 生成后，第一优先级不是看 ratio，而是看它是否已经撞到下一个 segment。

判断：
- 若存在下一个 segment，则计算 `max_safe_duration`
- 若 `initial_tts_duration > max_safe_duration`，则视为 `has_timeline_collision = true`

#### 2.1 有 collision
有 collision 时，说明这个 segment 已经威胁 timeline safety，必须进入 correction path。

这里不先区分它是 preferred / acceptable / too_long / too_short，先统一判断：
- 是否能在 `max_time_stretch_ratio` 限制内，通过**压缩**消除 collision

若可以：
- 进入 stretch path

若不可以：
- 暂时保留 raw
- 后续在 compose 前只允许尝试 trim trailing silence
- 若 trim 后仍 collision，则最终进入 `manual_review`

这里的原则是：

> 有 collision 时，优先看“是否能通过有限压缩解除 collision”，而不是先看 duration label。

#### 2.2 没 collision
若没有 collision，再看时长质量。

- 若 `preferred`：直接接受
- 若 `acceptable`：直接接受，不再继续 stretch
- 若 `too_short / too_long`：进入下一步，判断是否值得做 bounded stretch
- 若 target 非法或其他异常：直接 `manual_review`

这里明确：

> `acceptable` 且无 collision = 直接接受。

不为了把 `acceptable` 进一步优化成 `preferred` 而额外做 stretch。

### Step 3：判断是否允许 stretch
进入 correction path 后，判断是否允许做 bounded time-stretch。

允许 stretch 的条件建议收敛为：

1. `enable_time_stretch = true`
2. 当前结果需要 correction
3. `target_duration > 0`
4. 所需修正比例不超过 `max_time_stretch_ratio`
5. stretch 方向合理：
   - 有 collision 时：只考虑压缩
   - 没 collision 且 `too_long`：考虑压缩
   - 没 collision 且 `too_short`：考虑拉长
6. stretch 预期能带来实际改善：
   - 消除 collision
   - 或把结果从 `too_short / too_long` 拉回到 acceptable 区间

这里的核心思想是：
- `max_time_stretch_ratio` 是 stretch 的主约束
- 不再额外引入太多 eligibility 参数
- 能小修就修，不能小修就接受结果并显式标记问题

### Step 4：执行 stretch（若允许）
若 stretch 条件成立：
- 计算所需 stretch ratio
- 对 raw wav 做 bounded time-stretch
- 生成最终 TTS 文件
- 重新测量 stretch 后时长
- 更新：
  - `tts_duration`
  - `duration_error_seconds`
  - `time_stretch_ratio`
  - `correction_actions += ["time_stretch"]`

若 stretch 条件不成立：
- 不做 stretch
- `tts_path` 暂时保持 raw 结果

### Step 5：根据最终音频给出最终状态
在 raw 或 stretch 之后，重新基于**最终音频时长**和**是否 collision**给出最终状态。

#### 5.1 若仍有 collision
- 暂不立刻定为最终状态
- 进入 Step 6 的 compose 前处理，尝试只移除 trailing silence
- 若处理后仍 collision，则最终标记 `manual_review`

#### 5.2 若没有 collision
则只按时长质量判断：
- `preferred`：误差很小
- `acceptable`：误差在容忍范围内
- `too_short`：偏短但不影响 timeline safety
- `too_long`：偏长但不影响 timeline safety

这里要明确：
- `too_short / too_long` 不等于失败
- 它们表示结果不理想，但仍可继续跑 pipeline
- 只有遇到**严重 collision 无法消除**、或**其他严重异常**，才升级为 `manual_review`

### Step 6：compose 前 timeline-safe 处理
此阶段只做两类事：
- pad silence
- trim trailing silence

不会做：
- voiced content 裁剪
- 再次 stretch
- 文本改写

#### 6.1 提前结束
如果 `final_duration < target_duration` 且允许补静音：
- 不改 voiced audio
- 在 compose 时补尾静音
- 记录 `correction_actions += ["pad_silence"]`

注意：
- 这不是为了“伪装已经对齐”
- 而是为了让 segment 的时间结构更稳定，避免过早空出来影响整体节奏

#### 6.2 轻微 overhang
如果 `final_end <= next_segment.start + allowance`：
- 允许直接保留
- 不做额外处理

#### 6.3 明显 collision
如果 `final_end > next_segment.start + allowance`：
- 先尝试移除 trailing silence
- 若移除 trailing silence 后变安全：
  - 接受结果
  - 记录 `trim_trailing_silence`
  - 保持原有 `duration_status`（通常是 `acceptable` / `too_long`）
- 若仍不安全：
  - 不裁 voiced content
  - 最终标记 `manual_review`

### Step 7：manual review 与 repair 流程
`manual_review` 不阻断主 pipeline。

#### 7.1 主 pipeline 行为
当某个 segment 最终被标记为 `manual_review` 时：
- pipeline 继续运行
- 仍然生成 transcript / manifest / 合成结果
- 但在 artifacts 中显式记录这个 segment 需要人工处理

这样做的目的不是“忽略问题”，而是：
- 让整体试听和问题定位继续进行
- 不因为少数难例阻断整条管线

#### 7.2 repair artifact
建议额外落一个 repair 输入文件，例如：
- `runs/<job-id>/manual_review_segments.json`

每条记录至少包含：
- `segment_id`
- `start`
- `end`
- `text_en`
- `text_kk`
- `target_duration`
- `initial_tts_duration`
- `tts_duration`
- `duration_error_seconds`
- `has_timeline_collision`
- `duration_status`
- `correction_actions`
- `raw_tts_path`
- `tts_path`

#### 7.3 repair script
后续建议单独提供 repair script，而不是把 repair 混进主 pipeline。

repair script 负责：
- 读取 `manual_review_segments.json`
- 允许人工修改问题 segment 的 `text_kk` 或 repair 指令
- 只对指定 segment 重新跑 TTS / 对齐 / compose replacement
- 将修复后的 segment 音频替换回当前 run 的 artifacts

这里明确不建议：
- 在主 pipeline 里反复 prompt TTS 模型“请更短一点 / 更长一点”
- 在 TTS 阶段做 post-translation rewrite loop

原因是这会破坏当前已确认的边界：
- 文本长度控制只属于 translation prompt 阶段
- TTS 阶段只负责音频测量、有限修正、时间线安全处理、metadata 落盘

---

## 5. 模块与函数职责建议

下面是建议的职责切分，尽量复用现有结构，避免过度设计。

---

## 5.1 `providers/gemini_translate_provider.py`

### 职责
- 读取 translation prompt
- 执行英文到哈语翻译
- 不感知 TTS duration logic

### 不负责
- 不根据 TTS 结果回改文本
- 不做 segment 时长判断
- 不做 bucket prompt 分流

---

## 5.2 `services/synthesis.py`

### 职责
这是完整对齐策略的**核心编排模块**。

它应负责：
- raw TTS 生成
- 初始 timeline collision 判断
- 时长质量判断
- 判断是否进入 stretch path
- 执行 bounded stretch（若允许）
- 写回 segment metadata
- 输出最终 TTS 文件

### 建议拆分函数

#### 1. 基础计算函数（纯函数）
- `compute_target_duration(segment) -> float`
- `compute_duration_ratio(target_duration, actual_duration) -> float | None`
- `compute_duration_error(target_duration, actual_duration) -> float | None`
- `compute_max_safe_duration(segment, next_segment, config) -> float | None`
- `has_timeline_collision(segment, next_segment, actual_duration, config) -> bool`
- `is_duration_preferred(target_duration, actual_duration, config) -> bool`
- `is_duration_acceptable(target_duration, actual_duration, config) -> bool`
- `classify_duration_only(target_duration, actual_duration, config) -> str`
- `compute_required_time_stretch_ratio(target_duration, actual_duration) -> float | None`
- `can_apply_time_stretch(required_ratio, config) -> bool`

#### 2. I/O 辅助函数
- `measure_wav_duration(path) -> float`
- `synthesize_raw_segment(segment, output_path, voice) -> Path`
- `apply_time_stretch(input_path, output_path, ratio, sample_rate) -> Path`

#### 3. 单 segment 主流程
- `process_segment(segment, next_segment, tts_dir, raw_dir, voice) -> Segment`

#### 4. 批量流程
- `run(transcript, tts_dir, voice) -> TranscriptDocument`

---

## 5.3 `services/audio_compose.py`

### 职责
这个模块只负责：
- compose 前的最后一层 timeline-safe handling
- 生成 ffmpeg compose 命令
- 执行 compose

### 不负责
- 不负责 raw TTS 生成
- 不负责判断是否 stretch
- 不负责 stretch ratio 计算
- 不负责文本修复或人工 repair 流程

### 建议拆分函数
- `prepare_segment_for_compose(segment, next_segment) -> Segment`
- `prepare_transcript_for_compose(transcript) -> TranscriptDocument`
- `trim_trailing_silence_if_possible(path, max_duration, config) -> TrimResult`
- `build_ffmpeg_command(transcript, output_path) -> str`
- `compose(transcript, output_path) -> Path`

### 关键原则
- compose 层只做最后安全处理
- 不回头改变前面 TTS correction 的决策
- 只做：
  - pad silence
  - 允许 minor overhang
  - trailing silence trim
  - 失败时标 `manual_review`

---

## 5.4 `ffmpeg/commands.py`

### 职责
- 根据已经准备好的 segment 元数据，构造 ffmpeg filter
- 不承担策略判断

### 只消费这些结果
- `segment.start`
- `segment.tts_path`
- `segment.tts_duration`
- `segment.target_duration`
- 是否需要在 compose 时 `pad_silence`

### 不负责
- 不做 stretch 判断
- 不做 collision 判断
- 不做 correction 策略编排

---

## 5.5 `pipeline.py`

### 职责
- 串联 translation / tts / compose / mux
- 输出 run-level summary
- 持久化 manifest / transcript
- 落盘 manual review repair artifact

### 建议输出内容
TTS 阶段后输出：
- total
- preferred
- acceptable
- too_short
- too_long
- manual_review
- average absolute duration error（可选）
- `time_stretch` 应用次数（可选）

同时在 run artifacts 中额外输出：
- `manual_review_segments.json`

---

## 5.6 `models/segment.py`

### 职责
保存 segment 级 metadata。

### 建议字段
当前已有：
- `target_duration`
- `initial_tts_duration`
- `tts_duration`
- `duration_status`
- `duration_error_seconds`
- `correction_actions`
- `time_stretch_ratio`

建议额外考虑两个字段：
- `raw_tts_path: Path | None`
- `has_timeline_collision: bool | None`

如果不想扩字段，也可以：
- `tts_path` 始终指最终音频
- raw path 和 collision 信息放到 manifest sidecar artifact

---

## 5.7 `config.py` / `default.yaml`

### 建议配置项
除了已有字段，完整策略建议使用以下配置：

```yaml
tts_alignment:
  enabled: true
  preferred_ratio_tolerance: 0.08
  max_ratio_tolerance: 0.15

  enable_time_stretch: true
  max_time_stretch_ratio: 0.08
  min_time_stretch_improvement_seconds: 0.05

  pad_with_silence: true
  allow_minor_overhang_seconds: 0.15
  trim_trailing_silence: true
  max_trailing_silence_trim_seconds: 0.25

  manual_review_on_failure: true
```

这里去掉了此前方案里偏冗余的 `short_ratio` / `severe_long_ratio`。

原因是策略已经收敛成：
- 是否必须 correction：先看 collision，再看时长是否超出 acceptable
- 是否可以 stretch：看所需修正量是否落在 `max_time_stretch_ratio` 内

这样参数更少，也更贴近现在确认下来的决策逻辑。

---

## 6. 推荐伪代码

## 6.1 TTS 对齐主流程

```python
def run_tts_alignment(transcript, voice, config, tts_dir, tts_raw_dir):
    result_segments = []

    for i, segment in enumerate(transcript.segments):
        next_segment = transcript.segments[i + 1] if i + 1 < len(transcript.segments) else None
        result_segments.append(
            process_segment(
                segment=segment,
                next_segment=next_segment,
                voice=voice,
                config=config,
                tts_dir=tts_dir,
                tts_raw_dir=tts_raw_dir,
            )
        )

    return transcript.copy(update={"segments": result_segments})
```

## 6.2 单 segment 主流程

```python
def process_segment(segment, next_segment, voice, config, tts_dir, tts_raw_dir):
    target_duration = max(0.0, segment.end - segment.start)
    if target_duration <= 0:
        return build_manual_review_segment(segment, reason="invalid_target_duration")

    raw_path = tts_raw_dir / f"{segment.id}.wav"
    provider.synthesize_segment(segment, raw_path, voice)

    raw_duration = measure_wav_duration(raw_path)
    raw_collision = has_timeline_collision(segment, next_segment, raw_duration, config)

    final_path = raw_path
    final_duration = raw_duration
    correction_actions = []
    time_stretch_ratio = None

    if raw_collision:
        required_ratio = compute_required_time_stretch_ratio_for_collision(
            segment=segment,
            next_segment=next_segment,
            actual_duration=raw_duration,
            config=config,
        )
        if required_ratio is not None and can_apply_time_stretch(required_ratio, config):
            stretched_path = tts_dir / f"{segment.id}.wav"
            apply_time_stretch(raw_path, stretched_path, required_ratio, config.tts.sample_rate)
            stretched_duration = measure_wav_duration(stretched_path)
            stretched_collision = has_timeline_collision(segment, next_segment, stretched_duration, config)
            if not stretched_collision:
                final_path = stretched_path
                final_duration = stretched_duration
                correction_actions.append("time_stretch")
                time_stretch_ratio = required_ratio
    else:
        raw_status = classify_duration_only(target_duration, raw_duration, config)
        if raw_status in {"too_short", "too_long"}:
            required_ratio = compute_required_time_stretch_ratio(target_duration, raw_duration)
            if required_ratio is not None and can_apply_time_stretch(required_ratio, config):
                stretched_path = tts_dir / f"{segment.id}.wav"
                apply_time_stretch(raw_path, stretched_path, required_ratio, config.tts.sample_rate)
                stretched_duration = measure_wav_duration(stretched_path)
                stretched_status = classify_duration_only(target_duration, stretched_duration, config)
                if stretched_status in {"preferred", "acceptable"}:
                    final_path = stretched_path
                    final_duration = stretched_duration
                    correction_actions.append("time_stretch")
                    time_stretch_ratio = required_ratio

    final_collision = has_timeline_collision(segment, next_segment, final_duration, config)

    if final_collision:
        final_status = "manual_review_placeholder"
    else:
        final_status = classify_duration_only(target_duration, final_duration, config)

    return segment.copy(update={
        "raw_tts_path": raw_path,
        "tts_path": final_path,
        "target_duration": target_duration,
        "initial_tts_duration": raw_duration,
        "tts_duration": final_duration,
        "duration_status": final_status,
        "duration_error_seconds": final_duration - target_duration,
        "correction_actions": correction_actions,
        "time_stretch_ratio": time_stretch_ratio,
        "has_timeline_collision": final_collision,
    })
```

## 6.3 compose 前准备

```python
def prepare_segment_for_compose(segment, next_segment, config):
    result = segment.copy()

    if result.tts_duration < result.target_duration and config.pad_with_silence:
        result.correction_actions.append("pad_silence")

    if next_segment is None:
        return result

    max_safe_duration = next_segment.start + config.allow_minor_overhang_seconds - result.start
    if result.tts_duration <= max_safe_duration:
        return result

    if config.trim_trailing_silence:
        trimmed = trim_trailing_silence_if_possible(
            path=result.tts_path,
            max_duration=max_safe_duration,
            max_trim_seconds=config.max_trailing_silence_trim_seconds,
        )
        if trimmed.applied:
            result.tts_path = trimmed.output_path
            result.tts_duration = trimmed.duration
            result.duration_error_seconds = trimmed.duration - result.target_duration
            result.correction_actions.append("trim_trailing_silence")
            result.has_timeline_collision = result.tts_duration > max_safe_duration
            if not result.has_timeline_collision:
                if result.duration_status == "manual_review_placeholder":
                    result.duration_status = classify_duration_only(
                        result.target_duration,
                        result.tts_duration,
                        config,
                    )
                return result

    result.duration_status = "manual_review"
    result.has_timeline_collision = True
    return result
```

## 6.4 manual review artifact

```python
def write_manual_review_segments(transcript, output_path):
    rows = []
    for segment in transcript.segments:
        if segment.duration_status != "manual_review":
            continue
        rows.append({
            "segment_id": segment.id,
            "start": segment.start,
            "end": segment.end,
            "text_en": segment.text_en,
            "text_kk": segment.text_kk,
            "target_duration": segment.target_duration,
            "initial_tts_duration": segment.initial_tts_duration,
            "tts_duration": segment.tts_duration,
            "duration_error_seconds": segment.duration_error_seconds,
            "has_timeline_collision": segment.has_timeline_collision,
            "duration_status": segment.duration_status,
            "correction_actions": segment.correction_actions,
            "raw_tts_path": str(segment.raw_tts_path) if segment.raw_tts_path else None,
            "tts_path": str(segment.tts_path) if segment.tts_path else None,
        })
    write_json(output_path, rows)
```

---

## 7. 状态与 metadata 建议

### 7.1 每个 segment 建议保留的 metadata
- `target_duration`
- `initial_tts_duration`
- `tts_duration`
- `duration_status`
- `duration_error_seconds`
- `correction_actions`
- `time_stretch_ratio`
- `tts_path`
- `raw_tts_path`（建议新增，或 sidecar 持久化）
- `has_timeline_collision`（建议显式持久化）

### 7.2 `correction_actions` 推荐取值
- `time_stretch`
- `pad_silence`
- `trim_trailing_silence`

### 7.3 run-level summary 建议
- `total_segments`
- `preferred_count`
- `acceptable_count`
- `too_short_count`
- `too_long_count`
- `manual_review_count`
- `avg_abs_duration_error`
- `time_stretch_applied_count`
- `trim_trailing_silence_applied_count`
- `pad_silence_applied_count`

### 7.4 repair artifact
建议新增：
- `manual_review_segments.json`

---

## 8. 推荐实施顺序

如果准备一步到位做完整策略，我建议实现顺序是：

1. **先收敛状态模型和 config**
   - 明确 collision-first 决策
   - 明确 `manual_review` 的 repair 输出

2. **把 `synthesis.py` 做成 segment-level orchestrator**
   - raw TTS
   - collision 判断
   - 时长判断
   - bounded stretch
   - metadata 写回

3. **把 `audio_compose.py` 收敛成最后一层 timeline-safe handling**
   - pad silence
   - trailing silence trim
   - manual review 标记

4. **接 pipeline summary 与 artifacts**
   - manifest
   - transcript
   - `manual_review_segments.json`

5. **补齐测试**
   - pure helpers
   - stretch guardrail
   - collision-first 分支
   - trailing silence trim
   - repair artifact persistence

---

## 9. 我认为最需要你继续拍板的几个决策点

### 决策点 1：collision 是否作为显式字段持久化
我的建议：**是**。  
比如加 `has_timeline_collision`，不要把它完全隐含在 `duration_status` 里。

### 决策点 2：有 collision 时是否只允许压缩，不允许拉长
我的建议：**是**。  
因为 collision-first 分支的目标是解除时间线风险，不是追求更贴 target。

### 决策点 3：是否保留 raw tts artifact
我的建议：**保留**。  
完整策略里 raw/final 的差异非常重要。

### 决策点 4：trailing silence trim 的边界
我的建议：
- 只 trim 明确尾静音
- 限制最大 trim 秒数
- trim 后仍 collision 就 `manual_review`
- 永不裁 voiced content

### 决策点 5：repair script 是否只处理指定 segment
我的建议：**是**。  
不要重新跑整条 pipeline，而是只针对人工确认的问题 segment 做定点修复。

---

## 10. 一个更短的口径总结

推荐的完整策略可以概括为：

> 先用 translation prompt 控制译文长度；raw TTS 生成后先判断是否 collision；有 collision 时优先看能否通过有限压缩解除 collision；没 collision 时，preferred 和 acceptable 直接接受，too_short / too_long 只尝试 bounded stretch；compose 前只做 pad silence、允许轻微 overhang、必要时 trim trailing silence，永不裁 voiced content；manual_review 不阻断主 pipeline，而是额外落 repair artifact，后续通过单独 repair script 处理。

---

## 11. 供你继续用 `>>>` review 的建议方式

你可以继续在本文档里针对以下内容打 `>>>`：
- `has_timeline_collision` 是否要正式成为 `Segment` 字段
- collision-first 分支下是否只允许压缩
- `acceptable` 是否完全不再 stretch
- `manual_review_segments.json` 的字段是否还要补充
- repair script 的输入/输出形式是否要更具体
