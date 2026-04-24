好，就按“**先导航到目标区域**”这条主线走。

我建议你第一层先做成：

**导航到“放箱子的桌子 / 工位前”**

而不是：

* 直接找箱子
* 直接找小目标
* 直接为双臂服务

这样最稳，也最符合 NaVILA 的特性。

## 一、直接实施方案

### 场景设计

找一个室内场景，满足这几个条件：

* 有一张比较明显的桌子或工位
* 桌子上放一个空箱子，作为后续第二层任务的目标
* 桌边有椅子、显示器都可以，不用刻意清空
* 但整体不要太乱，桌子本身要容易成为导航 landmark
* 起始位置离桌子有一段距离，能体现“接近目标区域”的过程

你的第一层任务不是“识别箱子”，而是：

**走到那张桌子前**

### 第一层的成功标准

先不要追求特别复杂，成功标准就定成：

* VLM 连续输出的动作，整体能把机器人带到目标桌子前
* 到桌子前时，桌面区域明显变大
* 目标桌子基本在视野中央或接近中央
* 到达后可以停，或者切换到第二层近距离确认

### 数据准备

你现在先用两种测试方式就够了：

#### 方式 A：一次性 8 张图测试

适合先验证 prompt 和动作趋势是不是合理。

#### 方式 B：视频离散成连续图片测试

适合验证真实时序下，VLM 是否能连续把你带向目标区域。

### 任务分层

你后面整个系统建议分成三层：

#### 第一层：导航到目标区域

目标：桌子 / 工位 / 放箱子的区域

#### 第二层：近距离确认目标

目标：确认箱子是否在桌上、是否在操作范围内

#### 第三层：双臂动作

目标：抬起空箱子

现在只做第一层，不要混。

---

## 二、第一层推荐任务定义

建议你把任务定义成这种语义：

* `approach the desk with the empty box on it`
* `navigate to the workstation with the empty box`
* `move to the desk that has the box`

这里的关键是：

**箱子只是帮助描述目标区域，真正导航目标是“桌子 / 工位”**

这样比“find the empty box”稳得多。

---

## 三、推荐 prompt

你直接用下面这版 JSON。

```json id="qknbbm"
{
  "task": "approach the desk with the empty box on it",
  "target_object": "desk with the empty box",
  "prompt": "Task: approach the desk with the empty box on it.\n\nLook at the image history and decide the single best next navigation action to move toward the target area in this indoor scene.\nThe navigation target is the desk/workstation that has the empty box on it. Focus on approaching that desk area, not on precisely detecting the box itself from far away.\n\nUse the image history to infer whether the target desk area is on the left, on the right, near the center, or not clearly visible yet.\n\nNavigation priority:\n1. Prioritize turning to search for or align with the target desk area before moving forward.\n2. If the target desk area is visible on the left or right side, do not move forward yet. Turn first to align with it.\n3. Only move forward after the target desk area is roughly centered.\n4. If the target desk area is not clearly visible, first try turning to search for it.\n5. Only use move forward when the target desk area is near the center and still far away.\n6. If the robot has already approached the target desk area closely enough, output stop.\n\nIgnore irrelevant background details. Use the overall desk/workstation region as the navigation landmark.\n\nDo not explain your reasoning.\nDo not output any extra sentence.\nDo not output 'The next action is ...'.\nDo not output blank lines.\nOutput exactly 2 lines and nothing else.\n\nLine 1 format:\ntarget_state: <left/right/center/not visible>, <far away/near/very close>\n\nLine 2 format:\naction: <one action>\n\nThe action must be exactly one of:\n- turn left by 15 degrees\n- turn left by 30 degrees\n- turn left by 45 degrees\n- turn right by 15 degrees\n- turn right by 30 degrees\n- turn right by 45 degrees\n- move forward 25 centimeters\n- move forward 50 centimeters\n- move forward 75 centimeters\n- stop\n"
}
```

---

## 四、你现在怎么直接开始

### 第一步

拍一段“走向目标桌子”的第一视角视频。

要求：

* 起点离桌子稍远
* 桌子逐渐变大
* 中间可以有轻微左转或右转
* 最终目标桌子靠近视野中央

### 第二步

用你现在的 `video_to_frame_stream.py` 把视频离散成图片。

### 第三步

先做一次性 8 张测试：

```bash id="3w7m1b"
python test/navila_folder_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/navila_square_box_prompt.json \
  --images-dir test/navila_box_testset/your_video_name \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --once \
  --raw
```

### 第四步

如果一次性测试合理，再做连续图片测试：

```bash id="q2z3cz"
python test/navila_folder_stream_client.py \
  --host localhost \
  --port 54321 \
  --prompt-json test/navila_box_testset/navila_square_box_prompt.json \
  --images-dir test/navila_box_testset/your_video_name \
  --pattern "*.jpg" \
  --keep-last 8 \
  --sort-by name \
  --ingest-mode sequential \
  --require-full-window \
  --interval-sec 0.5 \
  --raw
```

---

## 五、你当前阶段最重要的判断标准

不是看它能不能立刻识别箱子。

而是看它能不能稳定做到这三件事：

* 看到目标桌子在左边时会左转
* 看到目标桌子在右边时会右转
* 目标桌子大致居中且仍较远时会前进

只要这三件事能稳定，你第一层就成了。

下一步你就可以在“桌子前”再加第二层：近距离确认箱子。
