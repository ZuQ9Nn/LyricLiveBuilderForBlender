# 03. LyricLiveBuilderForBlender 詳細設計書

| 項目 | 内容 |
|---|---|
| 版 | 0.1（初版・ドラフト） |
| 対象 | [02_specification.md](02_specification.md)（仕様書）の実装方法 |
| 読者 | 本アドオンの開発者・コントリビューター |

「要検証」と書いた項目は、試作（[04_work_procedure.md](04_work_procedure.md) の段階 0）で確かめてから実装を確定させます。

---

## 1. 設計方針

1. **計算と出力を分ける**：構成の決定と動きの計算は、Blender に依存しない純 Python（`core/`）で行います。結果を「ベイク済みのトラック」（§6）という中間データにします。Blender のプレビューと Unity の出力は、どちらもこの中間データから作ります。こうすると、プレビューと Unity の結果が食い違いません。
2. **Unity 側は「データを読んで組み立てるだけ」にする**：演出のロジックは Python 側に集め、C# は manifest（JSON）とメッシュ（バイナリ）を Unity のアセットに変換するだけにします。
3. **決定的**：乱数はすべてシードから作ります（`core/rng.py`）。同じ入力から同じ結果を出します。
4. **結合を小さくする**：`core/` は `bpy` を import しません。`mesh_optimizer/` は本体のモジュールを import しません。
5. **ファイルの大きさ**：1 ファイルは 300〜600 行を目安にします。部品（レイアウト・動き等）は種類ごとにファイルを分けます。

---

## 2. 全体構成

### 2.1 レイヤー

```
┌──────────────────────────── ui/ ─────────────────────────────┐
│ パネル・オペレーター・UIList・モーダル（タップ同期）            │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
┌──── text/ ────▼─────┐   ┌──── preview/ ──────▼─┐   ┌── export_unity/ ──┐
│ フォント解析(純Py)   │   │ ベイク済みトラック →   │   │ ベイク済みトラック → │
│ 字形メッシュ(bpy)    │   │ Blender のシーン       │   │ manifest/mesh/png  │
└──────────┬──────────┘   └──────────▲───────────┘   │ Unity 検出・起動    │
           │                         │               └─────────▲─────────┘
┌──────────▼──────────────── core/（bpy 非依存）──────────────────┴─────────┐
│ lyrics → timing/sections → planner/omakase → parts → bake（トラック生成）    │
│ audio（numpy）  rng  styles/moods/themes  synonyms                          │
└───────────────────────────────────────────────────────────────────────────┘
                      mesh_optimizer/（独立。本体からは公開関数だけを呼ぶ）
```

### 2.2 データの流れ

```
LLBProject（シーンのプロパティ）
   │ project_snapshot()：bpy のプロパティ → 純 Python の dict
   ▼
core.lyrics.parse() ─▶ ParsedLyrics（行・セクション見出し・記法）
core.audio.analyze() ─▶ AudioInfo（BPM・拍・音量・スペクトラム）
core.timing.compute() ─▶ Timing（行・文字の時刻、セクションの範囲）
core.planner.plan() ─▶ Plan（セクション・テーマ・行ごとの部品とパラメータ・ギミック・粒子）
   │ text.layout_metrics：文字の送り幅（フォント解析）を渡す
   ▼
core.bake.bake(plan, metrics) ─▶ BakedScene（オブジェクトの一覧 + 時刻つきのトラック）
   ├─▶ preview.build(baked)        … Blender のシーン
   └─▶ export_unity.export(baked)  … Unity の出力フォルダ
```

---

## 3. ディレクトリとモジュール

```
lyric_live_builder/
  blender_manifest.toml          # id, version, blender_version_min = "5.0.0", license = ["SPDX:MIT"], permissions
  __init__.py                    # register/unregister（サブモジュールの register を順に呼ぶ）
  prefs.py                       # AddonPreferences：Unity のパス、アセットライブラリ、遅延補正の既定値
  props.py                       # PropertyGroup（§4.1）
  i18n/
    __init__.py                  # bpy.app.translations.register
    ja_JP.py                     # 日本語の訳（msgid は英語）
  core/                          # bpy 非依存。numpy のみ使用
    rng.py                       # hash32 / Rng（mulberry32）/ easing / noise1
    lyrics.py                    # 記法の解析、セクション見出し、チャンク分割
    timing.py                    # 行・文字の時刻、拍スナップ
    sections.py                  # セクションの自動推定
    audio.py                     # PCM（numpy 配列）→ BPM・拍・音量・スペクトラム
    model.py                     # dataclass 定義（Plan・BakedScene ほか）
    styles.py / moods.py / themes.py   # 配色・雰囲気・テーマのデータ
    synonyms.py                  # キーワード → タグの同義語辞書
    registry.py                  # 部品のレジストリ（§5.6）
    planner.py                   # 構成の決定
    omakase.py                   # おまかせ・ここだけ変える
    bake.py                      # Plan → BakedScene（トラックのサンプリングと間引き）
    parts/
      layouts_basic.py           # 正面・見上げ・円弧・螺旋・互い違い・柱・散らし
      layouts_3d.py              # 斜めの壁・階段・床・立ち並ぶ・迫ってくる・立方体
      motions_enter.py / motions_hold.py / motions_exit.py
      particles.py               # パーティクルのプリセット定義
      backgrounds.py             # 背景・時間帯・トランジションの定義
      gimmicks.py                # 出し方の定義、内蔵基本形の一覧
  text/
    fontinfo.py                  # 純 Python：sfnt（TTF/OTF/TTC）の cmap / hmtx / vmtx / head / hhea の読み取り
    glyphs.py                    # bpy：文字 → メッシュ（2D/3D）、部品分解、キャッシュ
  preview/
    scene.py                     # コレクション、観客カメラ、作り直し
    objects.py                   # BakedScene のオブジェクト → Blender のオブジェクト
    animation.py                 # トラック → F カーブ（レイヤードアクション）
    materials.py                 # 文字・ドーム・ギミックのマテリアル（ノード）
    particles_gn.py              # パーティクルの近似表示（Geometry Nodes）
    gimmick_assets.py            # アセットライブラリのタグ索引・取り込み・正規化
  export_unity/
    exporter.py                  # 出力の全体制御
    convert.py                   # 座標・回転・色空間の変換（Blender → Unity）
    meshbin.py                   # 独自メッシュ形式の書き出し（§9.3）
    manifest.py                  # manifest の組み立て（§9.2）
    textures.py                  # パーティクルのアトラス、パノラマのコピー
    unity_locate.py              # Unity エディタの検出、プロジェクトのロック判定
    unity_run.py                 # バッチモードの起動と監視（タイマー）
    templates/                   # Unity にコピーする C# とシェーダー（§10）
  ui/
    panels.py / lists.py / operators_*.py / tap_sync.py
mesh_optimizer/                  # 独立パッケージ（§11）
  blender_manifest.toml          # 単体の Extension としてビルドする場合に使う
  __init__.py                    # 単体インストール時の register
  api.py                         # 公開関数
  retopo.py / decimate.py / merge.py / ui.py
tests/
  core/                          # unittest（Blender 不要）
  blender/                       # Blender をバックグラウンドで起動して実行するテスト
  unity/                         # サンプル manifest
```

依存のルール（違反は lint で検出します）：

| モジュール | import してよいもの |
|---|---|
| `core/` | 標準ライブラリ、numpy、`core/` 内 |
| `text/fontinfo.py` | 標準ライブラリ |
| `text/glyphs.py`, `preview/`, `export_unity/`, `ui/` | bpy、`core/`、`text/`、`mesh_optimizer.api` |
| `mesh_optimizer/` | 標準ライブラリ、bpy、bmesh、numpy（本体は import しない） |

---

## 4. データモデル

### 4.1 Blender のプロパティ（`props.py`）

`bpy.types.Scene.llb = PointerProperty(type=LLBProject)` に保存します（.blend に保存される）。

| PropertyGroup | 主なプロパティ |
|---|---|
| `LLBProject` | `lyrics_text`（Text への参照）、`fonts`（`LLBFontRole` × 4）、`audio_path`、`bpm`、`beat_offset`、`tap_latency_ms`、`seed`、`mood`、`style`、`fx`（`LLBFx`）、`extra`、`wa`、`sections`（Collection）、`lines`（Collection）、`enabled`（部品の ON/OFF：Collection）、`history`（おまかせの履歴：Collection）、`history_index`、`export`（`LLBExportSettings`） |
| `LLBFontRole` | `role`（display/serif/body/mono）、`filepath`、`font`（VectorFont への参照） |
| `LLBFx` | `motion`、`particles`、`decor`、`density`、`world_switch`、`koma`（0/12/8） |
| `LLBSection` | `kind`、`label`、`start`、`end`、`theme`、`locked` |
| `LLBLine` | `index`、`text`（表示用）、`start`、`end`、`char_times`（文字単位の時刻。JSON 文字列）、`section_index`、`is_3d`、`depth`、`bevel`、`layout`、`enter`、`hold`、`exit`、`distance_layer`、`persist`（次の行で消える/セクション末まで残る）、`particle_override`、`background_override`、`transition`、`gimmick`、`locked`、`seed_offset` |
| `LLBExportSettings` | `project_path`、`folder_name`、`use_tmp`、`use_mobile`、`use_udon_sync`、`material_mode`（VRCHAT/STANDARD）、`allow_other_2022_3` |

- 計算結果の Plan は、隠しテキストデータブロック `.llb_plan.json` に JSON で保存します。.blend を開き直しても、プレビューの作り直しと出力ができます。
- おまかせの履歴は、案ごとに「おまかせが変えた項目（雰囲気・スタイル・強さ・ON/OFF・配色・シード）」だけを JSON で持ちます。

### 4.2 Plan（`core/model.py`、dataclass）

```
Plan
  version, seed, duration, bpm, beats[], style_key, mood, fx
  sections[]  : SectionPlan(index, kind, start, end, theme_key, background, particles[], gimmicks[], transition_in)
  lines[]     : LinePlan(index, text, start, end, char_times[], section_index, is_3d, depth, bevel,
                         font_role, layout_key, layout_params, enter_key, enter_params, hold_key, exit_key,
                         distance, persist_until, emphasis, impact, seed)
  gimmicks[]  : GimmickPlan(source{kind: user|builtin|emblem, ref}, appear_key, at_time, until, position, scale, seed)
  particles[] : ParticlePlan(preset_key, params, start, end, emitter_shape, radius, intensity_curve[])
  events[]    : EventPlan(type: flash|burst|pulse, t, amp, dur)
```

### 4.3 BakedScene（`core/model.py`）

プレビューと Unity 出力の共通の入力です。座標は **Blender の座標系**（Z 上・正面 +Y・メートル）で持ちます。Unity 座標への変換は `export_unity/convert.py` だけが行います。

```
BakedScene
  duration, fps_hint
  nodes[] : Node(id, name, parent_id, category: text|particles|background|gimmicks,
                 kind: group|glyph|line_mesh|dome|far|gimmick|emitter,
                 mesh_ref, material_ref, rest: Transform, default_active=False)
  meshes{} : MeshSource(key, kind: glyph2d|glyph3d|piece|line|dome|builtin|user, build_args)
  materials{} : MaterialSpec(key, shader: unlit|lit|matcap|dome|particle_add|particle_alpha, params)
  tracks[] : Track(node_id, prop, interp: linear|constant, times: float32[], values: float32[N, C])
  emitters[] : EmitterSpec(node_id, preset, params)
  sections[] : (index, label, start, end)
```

トラックの `prop` は、次の種類に限定します（Blender と Unity の両方で表現できるもの）。

| prop | 成分 | 補間 | Blender | Unity |
|---|---|---|---|---|
| `active` | 1 | constant | `hide_viewport` / `hide_render` | `GameObject.m_IsActive` |
| `location` | 3 | linear | `location` | `m_LocalPosition`（変換） |
| `rotation` | 4（クォータニオン） | linear | `rotation_quaternion` | `m_LocalRotation`（変換） |
| `scale` | 3 | linear | `scale` | `m_LocalScale`（変換） |
| `color` | 4（RGBA） | linear | `color`（Object Info で読む） | `material._Color`（Renderer） |
| `emission` | 1 | linear | カスタムプロパティ `llb_emission` | `material._EmissionStrength` |
| `shape:<name>` | 1 | linear | シェイプキーの `value` | `blendShape.<name>` |
| `dome:<param>` | 1〜4 | linear/constant | ドームのカスタムプロパティ | `material._<Param>` |
| `emit_rate` | 1 | linear | GN 入力（近似） | `EmissionModule.rateOverTime.scalar` |

---

## 5. core の詳細

### 5.1 乱数（`rng.py`）

- JIZURA の `J.h()`（32bit ハッシュ）、mulberry32 系の乱数列、`range/int/pick/chance/wpick`、イージング（`E.*`）、`noise1` を移植します。
- JS の 32bit 演算（`Math.imul`、`>>> 0`）は、`& 0xFFFFFFFF` とマスク付きの乗算で再現します。ブラウザ版と同じ値になることを、移植元の既知の値で単体テストします（ただし、プラン全体の一致は保証しません：仕様書 01 の §4）。
- 動きの関数は、時刻の numpy 配列を受け取ります。そのため、ハッシュ乱数にも numpy でベクトル化した版を用意します。

### 5.2 歌詞の解析（`lyrics.py`）

- JIZURA の `parseLyrics` を移植し、セクション見出しを追加します。行の判定は次の順に行います。
  1. 空行 → 区切り（次の行の `gap_before`）
  2. `#` で始まる → コメント
  3. `^\[(ti|ar|al|by|offset):(.*)\]$` → メタ情報
  4. `^\[([^\]\d:][^\]:]{0,15})\]$`（数字・コロンを含まない短い角括弧だけの行）→ セクション見出し。名前を正規化表（仕様書 §5.1）で種別に変換し、表に無い名前は `custom` 種別として、見出しの文字列を残す
  5. 先頭の `[mm:ss.xx]` の並び → LRC の時刻
  6. それ以外 → 歌詞の行（`|注釈`、行末 `!`、`*強調*`、`/` を処理）
- チャンク分割は JIZURA の文字種ベースの分割（`Intl.Segmenter` が無い場合のフォールバック実装）を移植します。

### 5.3 タイミング（`timing.py`）とセクション推定（`sections.py`）

- 行の時刻：優先順位は「手動入力 > LRC > タップ同期 > 文字数と BPM からの推定」（JIZURA の `computeTiming` を移植）。タップの時刻からは `tap_latency_ms` を差し引きます。
- 文字単位の時刻：文字ごとの重み（かな 1.0、小書き 0.5、漢字 1.6、英数 0.6、記号 0.2、長音 0.8）で、行の歌い始めから「次の行の開始、または行の推定の長さ」までを配分します。文字単位のタップがあれば、それで上書きします。
- セクション推定（見出しが無い場合）：
  1. 候補の区切り＝空行、行の間の空きが 2 拍以上の位置。
  2. 各区切りの前後 4 秒の音量の平均の比を計算し、比が 1.35 以上の区切りを「盛り上がり」とする。
  3. 同じ歌詞の行の並び（2 行以上）が2回以上現れる範囲を、サビの候補とする。
  4. サビの候補 → `chorus`、その直前の区切り → `prechorus`、最初の行より前 → `intro`、最後の行より後 → `outro`、残り → `verse`。
  5. 最短 8 秒より短いセクションは、前のセクションに統合する。
- セクションは、曲の 0 秒から終わりまで、隙間なく並べます（Unity のクリップ分割の前提：§10.5）。

### 5.4 音声解析（`audio.py`）

- 入力：`aud.Sound(path).data()` で得た PCM の numpy 配列（形 [サンプル数, チャンネル数]）と、サンプリング周波数。読み込みは `ui` 側（bpy に依存するため）で行い、`core.audio` には配列だけを渡します。
- JIZURA の `analyzeAudio` を numpy でベクトル化して移植します（50Hz の音量、高域のオンセット、自己相関で BPM、位相探索）。
- 追加：帯域別の簡易スペクトラム。50Hz のフレームごとに FFT（2048 点）を取り、対数間隔の 24 帯域に集約して、0..1 に正規化します。ギミックのスペクトラムバーと、パーティクルの強さに使います。
- 長い曲（10 分）でも数秒で終わることを目標にします。PCM はモノラル化してから処理します。

### 5.5 プランナー（`planner.py`）

JIZURA の `plan()` をもとに、次の順で決めます。乱数は「シード × 段階 × 行番号」で分けます。こうすると、1つの段階を振り直しても、他の段階の結果は変わりません（「ここだけ変える」の実現）。

1. **テーマ**：セクションごとに、雰囲気とセクションの種別からテーマを重み付きで抽選します（同じ種別のセクションには、同じテーマを繰り返しやすくする：サビの反復の印象づけ）。テーマ＝{背景、パーティクルのプリセット 1〜3 個、ギミックの候補、配色の傾向}。
2. **行の構成**：行ごとにレイアウト・登場・保持・退場・距離の層・蓄積の有無を抽選します（JIZURA の `pickLayout/pickEnter/...` を移植。直近の重複回避と強調の補正を含む）。3D 文字の行は、3D 専用のレイアウトにも重みを付けます。
3. **ギミック**：行のチャンクに同義語辞書のキーワードが含まれれば、ギミックの候補にします（§8.3）。セクションごとの上限（既定 3）と、行の強調の度合いで出すかどうかを決めます。
4. **パーティクル**：テーマのプリセットをセクションの範囲に置き、行の `!`（インパクト）と強調でバーストのイベントを追加します。強さは音量の包絡から作ります（盛り上がりで増える）。
5. **背景の切り替え**：セクションの境目で背景を切り替え、テーマと雰囲気からトランジションを選びます。行の上書き（`background_override`）は、その行の開始で切り替えます。
6. **イベント**：フラッシュ（ドームの白飛び）、拍の脈動など。点滅は 1 秒あたり 3 回以下に抑えます（仕様書 §7.5）。

### 5.6 部品のレジストリ（`registry.py`）

```python
@register("layout", "front")
class FrontLayout(LayoutPart):
    name = "Front"            # msgid (translated via i18n)
    tags = ("calm", "pop", "editorial", "emotional", "glitch", "graphic")
    weight = 1.2
    supports_2d = True
    supports_3d = True
    only_3d = False
    def fits(self, n_chars: int, vertical: bool) -> bool: ...
    def plan(self, rng, ctx) -> dict: ...                  # JSON-serializable params
    def place(self, ctx, params) -> list[GlyphPlacement]:  # rest pose of each glyph
        ...
```

- `GlyphPlacement`：文字ごとの静止時の位置・回転・大きさ（行の親を基準）、表示順、縦書きでの回転の有無。
- 動きの部品は `evaluate(ctx, t: np.ndarray) -> Delta` を持ちます。`Delta` は、静止時の姿勢に足し込む位置・回転（クォータニオン）・拡大率・透明度・発光の配列です。登場は p=1、退場は p=0 で恒等になることを、全部品の単体テストで確かめます（JIZURA の部品の契約と同じ）。
- 部品の ON/OFF・追加分/和風の判定は、JIZURA の `randomOk` と同じ考え方で行います。

### 5.7 ベイク（`bake.py`）

1. ノードを作ります：行ごとに `group`、文字ごとに `glyph`（3D 文字なら `glyph3d` のメッシュ）。蓄積モードで、モバイル最適化 ON のときは `line_mesh` も作ります（§11.3）。
2. 文字ごとに、登場〜退場の範囲の時刻配列（既定 30Hz。コマ打ちのときはその間隔）を作り、静止姿勢に `Delta` を合成して、`location/rotation/scale/color` を計算します（numpy でベクトル化）。
3. `active` は表示の切り替わりの時刻だけを持ちます。
4. **間引き**：線形補間で許容誤差（位置 1 mm、回転 0.2°、拡大率 0.5%、色 1/255）を超えないように、Ramer–Douglas–Peucker 法でキーを減らします。
5. ドーム・パーティクル・ギミックも、同じトラックの形にします。

---

## 6. 文字（`text/`）

### 6.1 フォント解析（`fontinfo.py`）

- sfnt の表のうち、`head`（unitsPerEm）、`hhea`/`hmtx`（横の送り幅）、`vhea`/`vmtx`（縦の送り幅。無ければ 1em）、`cmap`（format 4 / 12）、`OS/2`（字面の高さ）を読みます。TTC は先頭のフォントだけを読みます（Blender の読み込みと合わせるため）。
- 用途：文字の送り幅、字形の有無の確認（不足文字の警告）。
- 純 Python（`struct`）で実装し、Blender 無しで単体テストします。

### 6.2 字形メッシュ（`glyphs.py`）

- 一時的なテキストカーブを作り（`body=1文字`、`size=1`、`align_x='LEFT'`、`align_y='TOP_BASELINE'`）、`resolution_u`（既定 6、モバイル時 4）を設定して、評価済みのメッシュ（`evaluated_get().to_mesh()`）を取り出します。
  - 2D：`extrude=0`、`fill_mode='BOTH'`。
  - 3D：`extrude = 厚み/2`、`bevel_depth`、`bevel_resolution=1`。
- 原点の合わせ方：送り幅（fontinfo）の中心と、`OS/2` の字面の上下の中心を原点にします。
- 大きさ：Blender はフォントの head 表のバウンディングボックスの高さを 1 として拡大します。そのため、Blender の 1em ＝ `unitsPerEm / (head.yMax − head.yMin)` です（試作 S0-01 で確認）。em 基準の大きさ E で出すときは、`size = E / (unitsPerEm / (yMax − yMin))` にします。送り幅は hmtx の値にこの係数を掛ければ、Blender 自身の並びと一致します。
- キャッシュ：キーは `(フォントのパス, 文字, 2D/3D, 厚み, ベベル, 解像度, 最適化の有無)` です。メッシュのデータブロックを共有します。
- 部品分解：2D 面を bmesh で連結成分（島）に分け、島ごとのメッシュ（原点＝島の重心）を作ります。分解→集合・爆散の動きで使います。
- 縦書き：送りは `vmtx`。長音・括弧などは JIZURA の `VERT_ROTATE` に従って 90° 回し、小書きの文字はずらします。

---

## 7. 空間配置と動き

### 7.1 座標と大きさ

- 観客点＝原点、目線＝(0, 0, `eye_height`)、正面＝+Y。
- 距離の層の既定：近景 1.2 m、中景 3.5 m、遠景 8 m（行の中心までの距離）。
- 文字の大きさは**視角**で決めます。`size = 2·d·tan(θ/2)`。θ の既定は、本文 2.5°、強調 4°、注釈 1.2° です。行の長さが水平の視野 70° を超える場合は、縮めるか改行します。
- 観客の方を向かせる：行の親を、観客の目線の方向に向けます（レイアウトがそれ以外の向きを指定する場合を除く）。

### 7.2 VR 向けの制約（ベイク時に強制）

| 制約 | 内容 |
|---|---|
| 近すぎ禁止 | 目から 0.6 m より内側には入れない（はみ出す位置は外へ押し出す） |
| ロール回転 | 空間全体（背景・床）のロール回転は使わない |
| 点滅 | 白飛びは 1 秒あたり 3 回まで、明るさの変化幅を制限する |
| 移動速度 | 空間全体が動く演出（トンネル等）は、見かけの速さに上限を設ける |

---

## 8. パーティクル・背景・ギミック

### 8.1 パーティクルのプリセット（`core/parts/particles.py`）

プリセットは dict で定義し、そのまま manifest に入れます。項目と、Unity の ParticleSystem との対応は次のとおりです。

| プリセットの項目 | Unity |
|---|---|
| `shape`（circle_dot/soft_dot/triangle/square/cross/hexagon/octagon/bubble/star/sparkle/petal/heart/note/snowflake/ring、または cube/hexprism/octahedron/icosahedron/shard/tetra） | 2D：Renderer=Billboard、アトラスの UV（TextureSheetAnimation の Sprite モード、タイル固定）／3D：Renderer=Mesh |
| `emitter`（cone_floor/hemisphere_sky/ring/box/sphere/text_mesh）、`radius`、`height` | ShapeModule |
| `rate`、`burst` | EmissionModule |
| `lifetime`、`speed`、`size`、`gravity`（範囲） | MainModule（MinMaxCurve の TwoConstants） |
| `color`（スタイルの配色の役割名）、`color_over_life` | MainModule.startColor、ColorOverLifetime |
| `noise`、`rotation`、`size_over_life`、`trail`、`sub_burst` | 各 Module |
| `blend`（add/alpha） | マテリアル |
| `max_particles` | MainModule.maxParticles（モバイル時は比率で減らす） |

- 2D のテクスチャは、`export_unity/textures.py` が numpy で符号付き距離（SDF）から描きます（1024×1024、4×4 のタイル）。Blender のプレビューでも同じ画像を使います。
- プレビュー（`particles_gn.py`）：Simulation Zone で発生・移動・寿命を近似します。ビルボードは観客カメラの方向に向けます。乱数・ノイズは Unity と同じにはなりません（見た目の確認用）。

### 8.2 背景ドーム

- メッシュ：アイコスフィア（細分化 3、半径 60 m）の法線を内側に向けたもの。UV は正距円筒（パノラマ画像用）。
- シェーダーは不透明・`Cull Front`・**`ZWrite On`** にします。Unity は不透明物の後に、深度が最も遠いままの画素へ Skybox を描きます。そのため、深度を書かないドームは Skybox に上書きされて見えなくなります（試作 S0-07 で確認）。
- シェーダーのパラメータ（A と B の2組＋進行度）

| パラメータ | 内容 |
|---|---|
| `_ModeA/_ModeB` | 0 単色 / 1 上下グラデ / 2 帯グラデ / 3 模様 / 4 画像 |
| `_Top/_Horizon/_Bottom`（A・B 各組） | グラデーションの 3 色 |
| `_BandCount`、`_PatternId`、`_PatternScale` | 帯・模様 |
| `_TexA/_TexB` | パノラマ画像 |
| `_TransType` | 0 クロスフェード / 1 上ワイプ / 2 下ワイプ / 3 横ワイプ / 4 リング / 5 ディゾルブ |
| `_Progress`、`_Softness` | 切り替えの進行度と、境界のぼかし幅 |
| `_Flash` | 白飛びの量（0..1） |

- 切り替えの手順：切り替え前に B へ次の背景を設定 → `_Progress` を 0 → 1 → 完了時に A へ B をコピーし、`_Progress` を 0 に戻す（同じフレームで行うので、見た目は変わらない）。
- Blender のプレビュー：同じロジックのシェーダーノードを組みます。パラメータは、ドームのオブジェクトのカスタムプロパティを Attribute ノード（種類：Object）で読みます。
- 遠景オブジェクト：月・太陽・山並み・街並みのシルエット・水平線を、プリミティブから生成します（unlit）。

### 8.3 ギミック

- **物体の解決**（仕様書 §8.3.1）：`resolve(keyword) -> GimmickSource`
  1. ユーザーのタグ索引（`preview/gimmick_assets.py`）
  2. 内蔵の基本形の表（`core/parts/gimmicks.py`。生成は `text/`・`preview/` 側の bmesh 関数）
  3. 紋章（キーワードを 3D 文字で作り、台座の円盤と組み合わせる）
- **同義語辞書**（`synonyms.py`）：`{tag: [語, ...]}` の形にします。照合は、歌詞のチャンクをひらがな・カタカナに正規化してから、部分一致で行います。利用者の追加分は、プリファレンスに JSON で保存します。
- **タグ索引**：「ライブラリを更新」で、指定したアセットライブラリの .blend をすべて調べます。調べ方は `bpy.data.libraries.load(path, link=True, assets_only=True)` でオブジェクトを一時的にリンクし、`asset_data.tags` を読んで、すぐライブラリを外す、です。結果（ファイル・名前・タグ）を、Extension のユーザーディレクトリの JSON に保存します。100 個で 0.02 秒です（試作 S0-10）。後始末はライブラリを外すだけにし、`bpy.data.orphans_purge()` は使いません（利用者の未使用データまで消すため）。利用者のファイルが既に同じライブラリをリンクしている場合は、ライブラリを外しません。
- **取り込みと正規化**：使うときに append し、評価済みのメッシュを1つにまとめます。そのうえで、高さを既定の大きさ（1.5 m）に、原点を底面の中心に、正面を +Y にそろえます。テクスチャ付きのマテリアルは、ベースカラーのテクスチャと色だけを引き継ぎます（Unity では lit / unlit に置き換える）。
- **出し方**：出し方ごとに、時刻の関数でトラックを作ります（床から：Z を -高さ → 0、空から：Z を +5 m → 0 で弾む、壁から：半径 6 m → 配置半径、ポップ：拡大率 0 → 1.15 → 1、ひっくり返る：床の板の X 回転 180°、開く：シェイプキー、溶けて消える：ドームと同じディゾルブのパラメータを物体のマテリアルで使う）。
- **スペクトラムバー**：24 本を半径 4 m の円に並べ、`audio.py` のスペクトラムから拡大率の Z のトラックを作ります（間引きつき）。

---

## 9. Unity への出力（Python 側）

### 9.1 出力フォルダ

```
<Project>/Assets/LyricLive/
  Editor/                     # 組み立てスクリプト（版をそろえて上書き。曲をまたいで共有）
  Runtime/                    # 同梱シェーダー、Udon 同期の元スクリプト
  Songs/<曲名>/
    manifest.json
    meshes.bin
    textures/particles_atlas.png, panorama_*.png
    audio/<曲ファイル>
    _pending.llb              # 未組み立ての印（組み立て後に削除）
    Generated/                # Unity 側が生成：Meshes/ Materials/ Clips/ <曲名>.playable / <曲名>.prefab
```

- `Editor/` と `Runtime/` は、アドオンの版より古い場合だけ上書きします（各フォルダの `version.txt` で判定）。
- 出力の前に `Songs/<曲名>/` の中身を確認し、`Generated/` が既にあれば上書きの確認ダイアログを出します（仕様書 §9.2-4）。

### 9.2 manifest（JSON）

Unity の `JsonUtility` で読めるように、辞書と入れ子の配列は使いません。数値の配列は平らにします。

```json
{
  "format": "llb-manifest", "version": 1, "generator": "LyricLiveBuilderForBlender 0.1.0",
  "song": { "title": "", "artist": "", "audio": "audio/song.wav", "duration": 215.3, "bpm": 128.0 },
  "options": { "tmp": false, "mobile": false, "udonSync": false, "materialMode": "VRCHAT" },
  "sections": [ { "index": 0, "label": "Intro", "kind": "intro", "start": 0.0, "end": 12.4 } ],
  "meshes": [ { "key": "g_00a1", "offset": 0, "length": 5120, "blendShapes": [] } ],
  "materials": [ { "key": "m_text0", "shader": "unlit", "color": [1,1,1,1], "emission": 0.0, "texture": "" } ],
  "nodes": [ { "id": 12, "name": "L003_c02_空", "parent": 11, "category": "text", "kind": "glyph",
               "mesh": "g_00a1", "material": "m_text0", "p": [0,0,0], "r": [0,0,0,1], "s": [1,1,1],
               "tmp": "", "tmpFont": "" } ],
  "emitters": [ { "node": 40, "preset": "{...JSON 文字列...}" } ],
  "dome": { "node": 2, "mesh": "dome", "material": "m_dome" },
  "clips": [ { "section": 0, "category": "text",
               "curves": [ { "node": 12, "prop": "scale", "interp": 0, "components": 3,
                             "times": [0.0, 0.1], "values": [0,0,0, 1,1,1] } ] } ]
}
```

- `nodes[].p/r/s` と `curves[].values` は、**Unity の座標系に変換済み**です（§9.4）。
- `clips` は §10.5 の規則で、セクション × 分類に切り分けて出力します。
- パーティクルのプリセットは入れ子が深いので、JSON の文字列として埋め込み、C# 側で専用のクラスに `JsonUtility.FromJson` します。

### 9.3 独自メッシュ形式（`meshes.bin`）

リトルエンディアン。メッシュをつなげて1ファイルにし、manifest の `offset/length` で参照します。

```
Mesh :=
  magic    : char[4] = "LLBM"
  version  : u16 = 1
  flags    : u16            # bit0 normals, bit1 uv0, bit2 colors, bit3 index32
  nVerts   : u32
  nIndices : u32
  nShapes  : u16
  reserved : u16
  positions: f32[nVerts*3]  # Unity space
  normals  : f32[nVerts*3]  # if bit0
  uv0      : f32[nVerts*2]  # if bit1
  colors   : u8[nVerts*4]   # if bit2
  indices  : u16|u32[nIndices]   # triangles, Unity winding (clockwise)
  shapes   : Shape[nShapes]
Shape :=
  nameLen  : u16, name: utf8[nameLen]
  deltaPos : f32[nVerts*3]  # delta, Unity space
```

- 頂点は、角の法線（フラットシェーディング）が必要な辺で分割してから書き出します（Blender のループ単位 → Unity の頂点単位）。

### 9.4 座標変換（`convert.py`）

| 量 | Blender → Unity |
|---|---|
| 位置 | `(x, y, z) → (x, z, y)` |
| クォータニオン | `(w, x, y, z) → Unity (x, y, z, w) = (-x, -z, -y, w)` |
| 拡大率 | `(sx, sy, sz) → (sx, sz, sy)` |
| 三角形の巻き順 | 反転（鏡映変換のため） |
| 色 | 線形 ↔ sRGB：manifest は sRGB（Unity の Color はガンマ空間の値として扱う。プロジェクトの Color Space が Linear の場合も、`Color` の値として sRGB を渡す） |

- 変換の正しさは、左右・上下・前後が非対称なテスト用メッシュ（「F」の字の立体）と、回転のトラックで、Unity 上の見た目を確かめます（段階 0）。

### 9.5 Unity の検出（`unity_locate.py`）

探す順番：

1. プリファレンスで指定したパス
2. `C:\Program Files\Unity\Hub\Editor\2022.3.22f1\Editor\Unity.exe`
3. `%APPDATA%\UnityHub\secondaryInstallPath.json` に書かれたフォルダ ＋ `\2022.3.22f1\Editor\Unity.exe`
4. `%APPDATA%\UnityHub\` の editors 系の JSON（Hub の版によっては存在しない。試作 S0-04 の環境には無かった。見つかれば使う補助の手段とし、寛容に読む）
5. macOS：`/Applications/Unity/Hub/Editor/<ver>/Unity.app/Contents/MacOS/Unity`、Linux：`~/Unity/Hub/Editor/<ver>/Editor/Unity`

- 見つからなければエラーダイアログ（`invoke_popup`）を出します。2022.3.22f1 が無く、他の 2022.3 系がある場合は、確認ダイアログで続行するかを選ばせます。
- **ロック判定**：`<Project>/Temp/UnityLockfile` が存在し、書き込みで開けない（Windows では使用中で開けない）場合は、エディタが開いていると判断します。存在しても開ける場合は、残骸とみなします。

### 9.6 バッチモードの起動（`unity_run.py`）

```
Unity.exe -batchmode -nographics -quit -projectPath "<Project>"
          -executeMethod LyricLive.Editor.LLBBuilder.BuildFromCommandLine
          -llbSong "Assets/LyricLive/Songs/<曲名>" -logFile "<Project>/Logs/llb_build.log"
```

- `subprocess.Popen` で起動し、`bpy.app.timers` で 0.5 秒ごとに終了とログを確認します（Blender の画面を止めない）。
- ログの `[LLB]` で始まる行を進捗・警告として表示します。終了コードが 0 以外ならエラーダイアログを出し、ログのパスを示します。
- 初回は Unity の起動（コンパイルとインポート）に数分かかるので、タイムアウトは長め（既定 30 分）にし、中止ボタンを付けます。

---

## 10. Unity 側（`templates/`）

### 10.1 ファイル

| ファイル | 役割 |
|---|---|
| `Editor/LLBBuilder.cs` | 入口。`BuildFromCommandLine()`、`Build(songFolder)`、メニュー `Tools/LyricLive/Rebuild` |
| `Editor/LLBAutoBuild.cs` | `[InitializeOnLoad]` と `AssetPostprocessor`。`_pending.llb` を見つけたら `EditorApplication.delayCall` で組み立てる |
| `Editor/LLBManifest.cs` | manifest のクラス（`[Serializable]`） |
| `Editor/LLBMeshReader.cs` | `meshes.bin` → `Mesh`（.asset）。シェイプキーは `AddBlendShapeFrame` |
| `Editor/LLBMaterialFactory.cs` | マテリアルの生成（VRChat の Mobile シェーダー／同梱シェーダー／標準。シェーダーが見つからない場合の代替） |
| `Editor/LLBParticleFactory.cs` | プリセット → ParticleSystem の各モジュール |
| `Editor/LLBAnimationFactory.cs` | `clips` → `AnimationClip`（`AnimationUtility.SetEditorCurve`） |
| `Editor/LLBTimelineFactory.cs` | `TimelineAsset`・トラック・クリップ・バインディング・マーカー |
| `Editor/LLBTextMeshProFactory.cs` | TMP のフォントアセット（静的アトラス）と、文字ごとの TMP |
| `Editor/LLBUdonSyncFactory.cs` | Udon 同期の生成（UdonSharp がある場合のみコンパイルされる。§10.7） |
| `Runtime/Shaders/LLB_Unlit.shader` | 色・発光・透明度・ディゾルブ |
| `Runtime/Shaders/LLB_Dome.shader` | §8.2 のドーム |
| `Runtime/Shaders/LLB_MatCap.shader` | 標準モード用の MatCap |
| `Runtime/Udon/LLBSync.cs.txt` | 同期スクリプトの元（拡張子を変えて、コンパイルされないように置く） |

### 10.2 組み立ての手順（`LLBBuilder.Build`）

1. manifest を読み、版を確認する。
2. `Generated/` を作り直す（以前の生成物を削除）。
3. メッシュ → マテリアル → テクスチャの取り込み設定（アトラスは Clamp・ミップマップあり）。
4. 階層を作る（ルート → 分類 → ノード）。分類のルートに Animator（Controller 無し）を付ける。ノードは既定で非表示（`default_active=False`）。
5. パーティクルの生成。
6. AnimationClip の生成（§10.5）。
7. Timeline の生成（§10.6）。ルートに PlayableDirector と AudioSource を付け、バインドする。
8. オプション：TMP 変換、Udon 同期。
9. Prefab として保存し、`_pending.llb` を削除する。`[LLB] done` をログに出す。

組み立ては、作業用の一時オブジェクトだけで行い、開いているシーンのオブジェクトには触れません。シーンに置いた Prefab のインスタンスは、Prefab の上書きで自動的に更新されます（S0-03 の試作で、名前でシーンを検索して削除する処理が、シーンに置いたインスタンスまで消した）。

### 10.3 マテリアルの対応

| 仕様上の種類 | VRCHAT モード | 代替（シェーダーが見つからない場合） | STANDARD モード |
|---|---|---|---|
| unlit | `LyricLive/Unlit`（同梱） | `VRChat/Mobile/Particles/Alpha Blended` 相当の色 | `LyricLive/Unlit` |
| lit | `VRChat/Mobile/Toon Lit` | `Standard` | `Standard` |
| matcap | `VRChat/Mobile/MatCap Lit` | `LyricLive/MatCap` | `LyricLive/MatCap` |
| particle_add / particle_alpha | `VRChat/Mobile/Particles/Additive`・`Alpha Blended` | `Particles/Standard Unlit` | `Particles/Standard Unlit` |
| dome | `LyricLive/Dome` | （Quest で同梱シェーダーが使えない場合）`VRChat/Mobile/Toon Lit` + 色のみ | `LyricLive/Dome` |

- `material._Color` 等のアニメーションの対象プロパティ名は、シェーダーごとの対応表で置き換えます（例：Toon Lit の色）。

### 10.4 アニメーションのプロパティ

| トラックの prop | `EditorCurveBinding` |
|---|---|
| active | `typeof(GameObject)`, `m_IsActive` |
| location | `typeof(Transform)`, `m_LocalPosition.x/y/z` |
| rotation | `typeof(Transform)`, `m_LocalRotation.x/y/z/w`（符号の連続性を出力時に補正済み） |
| scale | `typeof(Transform)`, `m_LocalScale.x/y/z` |
| color | `typeof(MeshRenderer)`, `material._Color.r/g/b/a` |
| emission | `typeof(MeshRenderer)`, `material._EmissionStrength` |
| shape:<name> | `typeof(SkinnedMeshRenderer)`, `blendShape.<name>`（×100） |
| emit_rate | `typeof(ParticleSystem)`, `EmissionModule.rateOverTime.scalar` |

- 補間：linear はキーの接線を前後の傾きに設定、constant は `AnimationUtility.SetKeyBroken` と `TangentMode.Constant` を使う。

### 10.5 クリップの分割規則

- クリップ＝「セクション × 分類」。範囲は `[section.start, section.end)` で、クリップ内の時刻は 0 から始めます。
- **クリップは自己完結させます。** Timeline の Animation Track は、そのとき再生中のクリップに含まれないプロパティを既定値に戻します。そのため、各クリップには、そのセクションで動く・見えるノードのすべてのプロパティを、開始時刻の値から入れます。
- セクションの境目をまたぐ要素（退場の途中の文字・続いている背景・パーティクル）は、両方のクリップに含め、境目の時刻の値をそろえます。
- 既定値（Prefab に保存される状態）は「すべて非表示・静止姿勢」です。

### 10.6 Timeline

| トラック | 種類 | バインド | クリップ |
|---|---|---|---|
| Audio | AudioTrack | ルートの AudioSource | 曲 1 本 |
| Text | AnimationTrack | `Text` の Animator | セクションごと |
| Particles | AnimationTrack | `Particles` の Animator | セクションごと |
| Background | AnimationTrack | `Background` の Animator | セクションごと |
| Gimmicks | AnimationTrack | `Gimmicks` の Animator | セクションごと |
| Markers | Marker Track | — | セクション名・行の Signal 用マーカー（編集の目印） |

- クリップ名：`<2桁の番号>_<セクション名>_<分類>`（例：`03_Chorus_Text`）。AnimationClip のアセット名も同じにします。
- PlayableDirector：`playOnAwake = true`（Udon 同期が OFF の場合）、`extrapolationMode = Hold`。

### 10.7 Udon 同期（オプション）

- UdonSharp が入っているかは、型 `UdonSharp.UdonSharpBehaviour` の有無で判定します。無ければ警告を出し、同期を付けずに続けます。
- 手順（スクリプトのコンパイルが要るので、2 段階で行います）
  1. `LLBSync.cs.txt` を `Generated/LLBSync_<曲名>.cs` にコピーし、`_pending_udon.llb` を置く。
  2. スクリプトの再読み込み後、`LLBAutoBuild` が UdonSharpProgramAsset を作り、Prefab に U# の部品を付けて、PlayableDirector と開始ボタンをつなぐ。
- 同期の内容：オーナーが「開始」を押す → 同期変数 `startServerTime`（`Networking.GetServerTimeInSeconds()`）と `isPlaying` を送る → 各クライアントは `director.time = now - startServerTime` にして `Play()` します。後から入室した人も、受信時に同じ計算で再生位置を合わせます。Udon からは再生速度を変えられないので、ずれが 0.2 秒を超えたときだけ `time` を設定し直します。
- U# の部品の付け方（試作 S0-11 で確立）：`UdonSharpProgramAsset` を `ScriptableObject.CreateInstance` で作って `sourceCsScript` を設定・保存 → `UdonSharpProgramAsset.CompileAllCsPrograms(forceCompile, editorBuild)` → `UdonSharpEditor.UdonSharpUndo.AddComponent(GameObject, Type)` → フィールドを設定して `UdonSharpEditorUtility.CopyProxyToUdon` で反映。U# の版の差を吸収するため、これらはリフレクションで呼び、見つからない場合は警告を出して同期を付けずに続けます。

### 10.8 TextMesh Pro

- 対象：2D 文字の行のうち、TMP 変換が ON の行（3D 文字の行はメッシュのまま）。
- フォントアセット：フォントファイルを一時的に `Generated/Fonts/` にコピーし、`TMP_FontAsset.CreateFontAsset` で作ります。歌詞で使う文字だけを `TryAddCharacters` で追加したら、`atlasPopulationMode = Static` にして、元のフォントへの参照を外します。最後にコピーしたフォントファイルを削除します（仕様書 §9.5）。
  - 外す参照は `m_SourceFontFile`・`m_SourceFontFileGUID`・**`m_SourceFontFile_EditorRef`** の 3 つです（`SerializedObject` で設定）。3 つめを外さないと、フォントファイルが依存に残ります（試作 S0-06）。
  - TMP の基本リソース（`Assets/TextMesh Pro`）が無いプロジェクトでは、TMP のシェーダーが無いためフォントアセットを作れません。無い場合は、`TMPro.TMP_PackageResourceImporter.ImportResources(true, false, false)` で自動的に取り込みます。
  - 作成したアトラスのテクスチャとマテリアルは、`AssetDatabase.AddObjectToAsset` でフォントアセットのサブアセットとして保存します。
- 文字ごとに TMP（`TextMeshPro`、1 文字）を作り、メッシュのノードの代わりに置きます。アニメーションのパスは同じにします（ノード名を変えない）。

---

## 11. モバイル最適化（`mesh_optimizer/`）

### 11.1 公開関数（`api.py`）

```python
def optimize_text_curve(curve_obj, *, resolution=4) -> None
def retopo_flat_text_mesh(mesh, *, dissolve_angle_deg=1.0, merge_dist=1e-5) -> RetopoReport
def extrude_flat_mesh(mesh, *, depth, bevel=0.0) -> None
def decimate(mesh, *, ratio=None, target_tris=None, planar_angle_deg=2.0) -> int
def merge_static_objects(objects, *, by_material=True) -> list
def bake_palette_material(objects, *, max_colors=64) -> PaletteResult
```

- 単体のアドオンとして入れた場合は、`ui.py` が 3D ビューのサイドバーに「Mesh Optimizer」パネルを出し、選択したオブジェクトに上の処理を行います。

### 11.2 文字のリトポロジー（`retopo.py`）

参考記事の手作業を、bmesh で次のように自動化します。

1. テキストの曲線の解像度を下げてメッシュにする（§6.2）。
2. `bmesh.ops.remove_doubles(dist=1e-5)` で近接頂点を結合する。
3. `bmesh.ops.dissolve_limit(angle_limit=1°, use_dissolve_boundaries=False)` で、同一平面の三角形を多角形にまとめ、ほぼ直線上の頂点を取り除く。
4. `bmesh.ops.triangulate(quad_method='BEAUTY', ngon_method='BEAUTY')` で三角形化し直す（細長い三角形を減らす）。

- 試作 S0-09 で、限定的溶解だけで穴が保たれることを確認しました（代表 100 字 × 2 書体 × 20 通りで、壊れた字は 0）。そのため、輪郭のループを取り出して面を張り直す手順は使いません。
- 既定値（試作 S0-09 で決定）

| 用途 | 曲線の解像度 | 角度 | 1 字の平均三角形数（ゴシック / 明朝） |
|---|---|---|---|
| 通常 | 6 | 1° | 100 / 303 |
| モバイル最適化 | 4 | 1° | 74 / 210 |

- 角度を 5° 以上にすると、明朝体で形の誤差が大きくなる（面積で最大 8%）ため、角度の上限は 3° にします。

### 11.3 行メッシュへの切り替え

- 対象：モバイル最適化が ON で、保持の動きが「静止」または行単位の動き（行全体の脈動など）の行。文字ごとに動く保持の行は切り替えません。
- ベイク時に、行の静止姿勢で全文字を結合した `line_mesh` ノードを作ります。登場が終わった時刻に、文字ノードを非表示・`line_mesh` を表示に切り替え、退場の開始時刻に逆に切り替えます。

### 11.4 目安の検査

出力の前に、BakedScene から次の値を数え、仕様書 §10.3 の上限を超えたら警告します。

- 各時刻で表示中の三角形の数
- パーティクルの最大数の合計
- マテリアルの数

---

## 12. Blender のプレビュー（`preview/`）

- コレクション：`LyricLive`（`Text`・`Particles`・`Background`・`Gimmicks`・`Camera`）。作り直しは、このコレクション以下のオブジェクト・メッシュ（共有キャッシュ以外）・アクションを削除してから行います。
- アニメーションの書き込み（`animation.py`）：Blender 5.x のレイヤードアクションの API を使います。
  - オブジェクトごとにアクションを作り、`fcurve_ensure_for_datablock` または `layers → strips → channelbag(slot)` の `fcurves.new()` で F カーブを作ります。
  - `keyframe_points.add(n)` と `foreach_set('co', ...)` でまとめて書き込み、補間を一括で設定します。
  - 実際の書き込み手順（試作 S0-02 で確定）：`action.slots.new(id_type='OBJECT')` → `action.layers.new()` → `layer.strips.new(type='KEYFRAME')` → `strip.channelbag(slot, ensure=True)` → `fcurves.new(data_path, index)` → `keyframe_points.add(n)` → `foreach_set('co', …)` と `foreach_set('interpolation', …)`（整数 1 ＝ LINEAR、0 ＝ CONSTANT）→ `fcurve.update()`。最後に `animation_data.action` と `animation_data.action_slot` を設定する。
  - 速さ：6 万キーで 0.04 秒、300 万キーで 2.8 秒（試作 S0-02）。
- マテリアル：文字は「Object Info の Color/Alpha × 発光」の共有マテリアル（オブジェクトごとのマテリアルを作らない）。透明は、マテリアルのレンダリング方法を Blended にします。
- 観客カメラ：原点・目線の高さ・正面 +Y・視野角 90°。
- 色の管理：シーンの色変換を Standard にします（作り直しの時に確認し、違えば変更を提案する）。

---

## 13. UI（`ui/`）

3D ビューのサイドバーに「LyricLive」タブを作り、作業の順にパネルを並べます。

| パネル | 内容 |
|---|---|
| 1. 歌詞 | 歌詞を開く（テキストエディタ）、記法のヘルプ |
| 2. フォント | 役割 × 4 のファイル指定、不足文字の警告 |
| 3. 曲 | 曲を読み込む、BPM・最初の拍、解析の再実行 |
| 4. 同期 | タップで同期、遅延の測定、マーカーから取り込み、文字単位の配分 |
| 5. おまかせ | おまかせで作る、前の案/次の案、ここだけ変える、使う演出の範囲 |
| 6. セクションと行 | セクションの UIList、行の UIList、選んだ行の詳細（仕様書 §6.2） |
| 7. 演出 | 強さのスライダー、部品の ON/OFF（分類ごとの UIList と絞り込み） |
| 8. プレビュー | 生成、削除、観客カメラ、目安の検査 |
| 9. Unity 出力 | プロジェクト、エディタ、オプション、出力、状態とログ |
| 最適化 | mesh_optimizer のパネル（独立） |

- タップ同期（`tap_sync.py`）：モーダルオペレーターです。開始時に `screen.animation_play` で再生し、`T` キーのイベントで `scene.frame_current + 小数（frame_float）` から時刻を求めて記録し、マーカーを置きます。`Esc` で終了、`Backspace` で取り消し。
- 遅延の測定：拍のクリック音のサウンドストリップを作って再生し、利用者に拍に合わせて 16 回タップしてもらいます。理論上の拍の時刻との差の中央値を `tap_latency_ms` にします。
  - キーリピート（`event.is_repeat`）は無視します。拍から 150 ms を超えてずれたタップは外れ値として除き、その回数を表示します。ばらつきは中央絶対偏差（MAD）で表示します（標準偏差は、最後のクリックの後のタップや二度押しで大きく膨らむため。S0-08）。
  - タップの時刻は `time.perf_counter()` で記録し、`frame_change_post` で記録した「フレームと実時間の組」の差の中央値で、曲の時刻に直します。AUDIO_SYNC では、フレームが 1 つおきに進んだり止まったりする（±17 ms の揺れ）ため、最後のフレームを基準にするより正確です。タップ同期でも同じ方法を使います。
- 長い処理（解析・おまかせ・プレビュー生成）は `wm.progress_begin/update/end` で進捗を出します。

---

## 14. 多言語

- コード上の文字列（msgid）は英語にします。`i18n/ja_JP.py` に日本語訳を開発の最初から用意するので、開発中も Blender の言語が日本語なら日本語で表示されます（仕様書の「開発中は日本語」を満たす）。
- 部品の名前も msgid（英語）とし、日本語訳を持ちます。
- 翻訳辞書の漏れは、テストで msgid を収集して検出します。

---

## 15. エラー処理とログ

| 状況 | 処理 |
|---|---|
| フォント未指定・字形の不足 | 実行前に検査し、ダイアログで不足を示す（不足文字は豆腐にならないよう、本文のフォントで代用） |
| 曲の読み込み失敗 | `aud` の例外を捕まえ、対応形式を案内する |
| Unity が見つからない | エラーダイアログ（仕様書 §9.2） |
| バッチモードの失敗 | 終了コードとログの `[LLB][ERROR]` 行を表示し、ログのパスを示す |
| 部品の実行時の例外 | その行だけ既定の部品（正面 / ポップ / 静止 / フェード）に置き換え、警告の一覧に追加する（全体は止めない） |

- ログは Python の `logging` で、Extension のユーザーディレクトリの `llb.log` に出力します（最大 1MB × 3 世代）。

---

## 16. テスト

| 対象 | 方法 |
|---|---|
| `core/` | `python -m unittest discover tests/core`（Blender 不要。numpy は必要） |
| `text/fontinfo.py` | テスト用の OFL フォント（リポジトリに置けるライセンスのもの）で、送り幅・cmap を検証 |
| 部品の契約 | 全部品について、登場の p=1・退場の p=0 で恒等になること、例外を出さないこと |
| Blender 側 | `blender --background --factory-startup --python tests/blender/run_all.py`：フォント → 文字メッシュ → プレビュー → 出力 |
| Unity 側 | `tests/unity/sample_manifest/` を Unity のテストプロジェクトに置き、バッチモードで `LLBBuilder.Build` を実行して Prefab の構造を検証 |
| 見た目 | 観客カメラで、決まった時刻のスクリーンショットを撮り、目視で確認する |

---

## 17. 仕様書からの変更点（本設計で反映済み）

| # | 変更 | 理由 |
|---|---|---|
| 1 | メッシュの受け渡しを FBX から独自形式に変更 | 軸変換・スケール・インポート設定のずれを避けるため（利用者の判断で決定） |
| 2 | 正面を -Y から +Y に変更 | Y と Z を入れ替えるだけで Unity 座標に変換できるようにするため |
| 3 | 背景ドームを 2 枚から 1 枚に変更（A/B の設定を持つシェーダー） | 半透明の全画面二重描画は Quest で重いため |
| 4 | Quest で同梱シェーダーが使えない場合の代替を追加 | 公式文書がワールドのカスタムシェーダーの可否を明記していないため |
| 5 | TMP は静的アトラスにし、フォントファイルをビルドに含めない | フォントの再配布になるのを避けるため |
| 6 | 行メッシュへの切り替えを追加（モバイル時） | 文字ごとのオブジェクトはドローコールが多いため |
| 7 | タップの遅延補正を追加 | Blender のイベント処理と音声出力の遅れを補正するため |
| 8 | .ttc は先頭の書体のみ | Blender のフォント読み込みの制約 |
| 9 | ステージの大きな変形はボーンを使わない | 独自形式のメッシュでボーンを扱わないため。部品の動きとシェイプキーで作る |

### 17.1 試作（段階 0）による確定事項

試作の結果は [05_prototype_results.md](05_prototype_results.md) にまとめています。本設計書では、§6.2・§8.2・§8.3・§9.5・§10.7・§10.8・§11.2・§12 に反映しました。
