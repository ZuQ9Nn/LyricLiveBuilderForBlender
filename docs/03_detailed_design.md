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
    model.py                     # dataclass 定義（Plan・BakedScene・Settings ほか）
    color.py                     # 色の変換、コントラストの補正、ランダムな配色（JIZURA から移植）
    styles.py / moods.py / themes.py   # 配色・雰囲気・テーマのデータ
    world.py                     # テーマ・背景・トランジション・パーティクル・フラッシュの計画（§5.5）
    meshes.py                    # 内蔵メッシュ（ドーム・遠景・3D パーティクル・光の玉）の numpy データ
    atlas.py                     # パーティクルの 2D テクスチャのアトラス（符号付き距離から描画）と PNG 出力
    synonyms.py                  # キーワード → タグの同義語辞書
    registry.py                  # 部品のレジストリ（§5.6）
    planner.py                   # 構成の決定
    omakase.py                   # おまかせ・ここだけ変える
    bake.py                      # Plan → BakedScene（トラックのサンプリングと間引き）
    bake_world.py                # ドーム・遠景・パーティクルの発生源のノードとトラック
    guide.py                     # 視線の誘導（判定と、光の筋・灯り・ドームのトラック。§8.4）
    bake_gimmick.py              # ステージギミックとスペクトラムバーのノードとトラック（§8.3）
    gimmick_shapes.py            # 内蔵の基本形の numpy データ（§8.3）
    parts/
      layouts_basic.py           # 正面・見上げ・円弧・螺旋・互い違い・柱・散らし
      layouts_3d.py              # 斜めの壁・階段・床・立ち並ぶ・迫ってくる・立方体
      motions_enter.py / motions_hold.py / motions_exit.py
      particles.py               # パーティクルのプリセット定義
      backgrounds.py             # 背景・時間帯・トランジションの定義
      gimmicks.py                # 出し方の定義、行ごとのギミックの計画、スペクトラムの区間
  text/
    fontinfo.py                  # 純 Python：sfnt（TTF/OTF/TTC）の cmap / hmtx / vmtx / head / hhea の読み取り
    glyphs.py                    # bpy：文字 → メッシュ（2D/3D）、部品分解、キャッシュ
  preview/
    scene.py                     # コレクション、観客カメラ、作り直し
    objects.py                   # BakedScene のオブジェクト → Blender のオブジェクト
    animation.py                 # トラック → F カーブ（レイヤードアクション）
    materials.py                 # 文字・ドーム・ギミックのマテリアル（ノード）
    particles.py                 # パーティクルの近似表示（毎フレーム core の式で計算してメッシュに書く。§8.1）
    gimmick_assets.py            # アセットライブラリのタグ索引・取り込み・正規化
  export_unity/
    exporter.py                  # 出力の全体制御
    convert.py                   # 座標・回転・色空間の変換（Blender → Unity）
    meshbin.py                   # 独自メッシュ形式の書き出し（§9.3）
    manifest.py                  # manifest の組み立て（§9.2）
    particles_unity.py           # 発生源の spec → Unity の ParticleSystem の説明（JSON）
    unity_locate.py              # Unity エディタの検出、プロジェクトのロック判定
    unity_run.py                 # バッチモードの起動と監視（タイマー）
    budget.py                    # 目安の検査（§11.4）
    templates/                   # Unity にコピーする C# とシェーダー（§10）
  ui/
    panels.py / lists.py / operators_*.py / tap_sync.py
    planning.py                  # シーンのプロパティ ⇔ おまかせの状態・Settings、鍵、プレビューの生成
  mesh_optimizer/                # 本体から独立したパッケージ（§11）。本体は相対 import で使う
    blender_manifest.toml        # 単体の Extension としてビルドする場合に使う（本体の zip からは除外）
    __init__.py                  # 単体インストール時の register
    api.py                       # 公開関数
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
| `LLBProject` | `lyrics_text`（Text への参照）、`font_display` / `font_serif` / `font_body` / `font_mono`（`LLBFontRole`）、`audio_path`、`audio_duration`、`duration`、`bpm`、`beat_offset`、`tap_latency_ms`、`latency_measured`、`sections_from_headings`、`seed`、`mood`、`style`、`fx`（`LLBFx`）、`use_accent`・`accent`（独自のアクセント色）、`stage_offsets`（段階ごとの振り直しの回数。「ここだけ変える」）、`sections`（Collection）、`lines`（Collection）、`parts`（部品の ON/OFF：`LLBPartToggle` の Collection）、`parts_kind`、`history`（おまかせの履歴：Collection）、`history_index`、`reroll_target`、`panorama_path`、`export`（`LLBExportSettings`。段階 4） |
| `LLBFontRole` | `filepath`（VectorFont への参照は、段階 2 の字形メッシュで読み込むときに作る） |
| `LLBFx` | `motion`、`particles`、`decor`、`density`、`world_switch`、`koma`（0/12/8）、`guide`（視線の誘導の強さ。0 で切）、`flash` |
| `LLBSection` | `kind`、`user_kind`（手で変えた種別。開始時刻が同じ間は、読み直しても残す）、`label`、`start`、`end`、`theme`・`background`・`transition`（AUTO＝おまかせ）、`locked`・`lock_frozen`（鍵で埋めた項目。外すと自動に戻す）。手で決めた項目も、開始時刻が同じ間は読み直しても残す |
| `LLBLine` | `index`、`text`（表示用）、`start`、`end`（決定した時刻）、`source`（auto/tap/lrc/manual）、`tap_time`（遅延を補正したタップの時刻。負の値＝未タップ）、`use_manual`・`manual_start`（手動の時刻）、`char_times`（文字単位の時刻。JSON 文字列）、`section_index`、`is_3d`、`depth`、`bevel`、`layout`、`enter`、`hold`、`exit`、`distance_layer`、`persist`（次の行で消える/セクション末まで残る）、`guide`（視線の誘導：自動/あり/なし）、`particle`、`background`、`transition`、`locked`・`lock_frozen`、`seed_offset`（この行だけ選び直した回数）。`gimmick` は段階 6 |
| `LLBExportSettings` | `project_path`、`folder_name`、`use_tmp`、`use_mobile`、`use_udon_sync`、`material_mode`（VRCHAT/STANDARD）、`allow_other_2022_3` |

- Plan は保存しません。決定的なので、プロパティから毎回同じ Plan を作れます（段階 4 で必要になったら保存する。改善メモ #8）。
- おまかせの履歴は、案ごとに「おまかせが変えた項目」の JSON（`{mood, style, fx, disabled, accent, seed, stage_offsets}`）を持ちます（最大 30 件）。「前の案」はこれをプロパティに戻して作り直します。
- 鍵：行の鍵は、その時点の Plan の値で「おまかせ」の項目を埋めます（レイアウト・登場・保持・退場・距離の層・消え方）。埋めた項目名を `lock_frozen` に記録し、鍵を外すとその項目だけ「おまかせ」に戻します。手で指定した項目は、鍵が無くてもおまかせで変わりません（仕様書 §6.2）。セクションの鍵も同じ（テーマ・背景・トランジション）。

### 4.2 Plan（`core/model.py`、dataclass）

```
Plan
  version, seed, duration, bpm, mood, style, fx{motion, particles, decor, density, world_switch, koma, guide, flash}
  sections[]      : (start, end)
  section_plans[] : SectionPlan(index, kind, start, end, theme, background(spec), particles[], palette{role: hex})
  world[]         : {t, dur, spec, transition}     背景の切り替え（最初の 1 件は t=0・トランジション無し）
  lines[]         : LinePlan(index, text, start, end, char_times[], section_index, emph_mask, is_3d, depth, bevel,
                             font_role, layout, layout_params, enter, hold, exit, enter_dur, exit_dur, distance,
                             persist, anchor, emphasis, seed, glide, colors{fg, accent}, guide, particle, impact)
  emitters[]      : {key, preset(強さで拡大縮小済み), start, end, seed, intensity[(t, v)], colors[], bursts[{t, origin}],
                     count(連続の粒の数), pool(破裂の粒の最大同時数), fade_in, fade_out}
  events[]        : {type: flash|pulse, t, amp, dur, color}
  gimmicks[]      : {line, tag, word, source: builtin|user|emblem, show, start, end, az, air, size, color, asset, role, accent}
  spectrum        : {levels, rate, windows[(start, end, rgb)]} または None
```

- 入力の `Settings`（`model.py`）：`mood`・`style`・`fx`・`disabled`（種類 → OFF の部品）・`stage_offsets`・`accent`・`energy`（音量の包絡）・`beats`・`panorama`（画像があるか）。おまかせの状態からは `core/omakase.settings()` で作ります。

### 4.3 BakedScene（`core/model.py`）

プレビューと Unity 出力の共通の入力です。座標は **Blender の座標系**（Z 上・正面 +Y・メートル）で持ちます。Unity 座標への変換は `export_unity/convert.py` だけが行います。

```
BakedScene
  duration, fps_hint
  nodes[] : Node(id, name, parent_id, category: text|particles|background|guide|gimmicks,
                 kind: group|glyph|line_mesh|dome|far|mote|glow|gimmick|emitter,
                 mesh_ref, material_ref, rest: Transform, default_active=False)
  meshes{} : MeshSource(key, kind: glyph2d|glyph3d|piece|line|dome|builtin|user, build_args)
  materials{} : MaterialSpec(key, shader: unlit|lit|matcap|dome|particle_add|particle_alpha, params)
  tracks[] : Track(node_id, prop, interp: linear|constant, times: float32[], values: float32[N, C])
  emitters[] : {node, spec}     パーティクルの発生源（spec は Plan.emitters の 1 件）
  guides[] : {line, t_on, t_hit, from, to, target, angle, kinds, color, motes}
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

ノードの `category` には、視線の誘導の `guide` も加えます（§8.4）。

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

- 行の時刻：優先順位は「手動入力 > LRC > タップ同期 > 文字数と BPM からの推定」（JIZURA の `computeTiming` を移植。JIZURA は全行に LRC がある場合だけ LRC を使うが、本アドオンは行ごとに判定する）。`tap_latency_ms` は、タップを記録するときに差し引いて `tap_time` に保存します（マーカーの位置と行の開始時刻を一致させるため。遅延を測り直しても、記録済みのタップは補正し直さない）。
- 歌詞を読み直したときは、前後の行の文字列を `difflib.SequenceMatcher` で照合し、タップと手動の時刻を同じ文字列の行に引き継ぎます（行を挿入・削除しても、以降の行の時刻がずれない）。行数の変わらない書き換え（誤字の修正など）は、順番どおりに引き継ぎます。行番号が変わったときは、マーカー `LLB:<行番号>` を付け直します（動かしたまま取り込んでいないマーカーの位置は失われる）。
- 文字単位の時刻：文字ごとの重み（かな 1.0、小書き 0.5、漢字 1.6、英数 0.6、記号 0.2、長音 0.8）で、行の歌い始めから「次の行の開始、または行の推定の長さ」までを配分します。文字単位のタップがあれば、それで上書きします。
- セクション推定（見出しが無い場合）：
  1. 区切り＝空行、行の間の空き（行の開始から推定の歌う長さを引いた残り）が「2 拍」かつ「その曲の空きの中央値 + 2 拍」以上の位置、各行の開始の前後 4 秒の音量の平均の比が 1.35 以上の位置（盛り上がり）。空きの基準を相対にしたのは、推定の歌う長さが実際より短く、固定の 2 拍ではほぼ全行が区切りになったため。
  2. 同じ歌詞の行の並び（2 行以上）が 2 回以上現れる行を、サビの候補とする。区切りの間の行の半分以上がサビの候補ならサビ。繰り返しが無い曲では、盛り上がりで始まった区間をサビとし、音量が開始時の 1/1.35 を下回るまで続ける。
  3. サビの直前に `verse` が 2 つ続く場合、直前の 1 つを `prechorus` にする。最初の行より前 → `intro`、行の間の空きが 8 秒以上 → `interlude`、最後の行を歌い終えた後 → `outro`、残り → `verse`。同じ種別が隣り合う区間はまとめる。
  4. 最短 8 秒より短いセクションは、先頭なら次のセクションに、それ以外は前のセクションに統合する。
- 見出しから作る場合：見出しごとに、その行の最初の開始時刻から始める。行の無い見出し（`[間奏]` 等）は、前の行を歌い終える推定の時刻から始める。最初の見出しより前の行は、暗黙の `verse` にする。開始時刻が同じになったセクションは、後の見出しを残す。
- セクションは、曲の 0 秒から終わりまで、隙間なく並べます（Unity のクリップ分割の前提：§10.5）。

### 5.4 音声解析（`audio.py`）

- 入力：`aud.Sound(path).data()` で得た PCM の numpy 配列（形 [サンプル数, チャンネル数]）と、サンプリング周波数。読み込みは `ui` 側（bpy に依存するため）で行い、`core.audio` には配列だけを渡します。
- JIZURA の `analyzeAudio` を numpy でベクトル化して移植します（50Hz の音量、高域のオンセット、自己相関で BPM、位相探索）。
  - JIZURA の高域フィルター（1 次の再帰型 `y = a·(y' + x − x')`、a=0.92）は、サンプルごとの計算になり numpy で一括処理できません。そのため、50Hz のフレームごとに FFT を取り、フィルターの振幅特性 |H|² を掛けてエネルギーを求めます（パーセバルの定理。フレーム内の循環の誤差は、オンセットの検出には影響しない）。
  - テンポの自己相関は、探索範囲（70〜180 BPM）の外側にも 1 つずつ値を計算し、範囲の端の山も放物線で補間します（JIZURA では 174 BPM が 176.5 になっていた）。
  - 歌詞の時刻は、曲の再生位置からの秒です。
- 追加（段階 3 で実装。使うのはパーティクルとギミックのため）：帯域別の簡易スペクトラム。50Hz のフレームごとに FFT（2048 点）を取り、対数間隔の 24 帯域に集約して、0..1 に正規化します。ギミックのスペクトラムバーと、パーティクルの強さに使います。
- 長い曲（10 分）でも数秒で終わることを目標にします。PCM はモノラル化してから処理します。

### 5.5 プランナー（`planner.py`）

JIZURA の `plan()` をもとに、次の順で決めます。乱数は「シード × 段階 × 行番号」で分けます。こうすると、1つの段階を振り直しても、他の段階の結果は変わりません（「ここだけ変える」の実現）。

段階の番号（`core/world.py`）：1 テーマ、2 文字の構成、3 パーティクル、4 背景、5 ギミック。「ここだけ変える」は、その段階の振り直しの回数（`stage_offsets`）だけを増やし、段階のシードを `h(シード, 1000 + 段階, 回数)` に替えます（回数 0 なら元のシード）。

1. **テーマ**（`world.pick_themes`）：セクションごとに、雰囲気とセクションの種別からテーマを重み付きで抽選します（同じ種別のセクションは 70% で同じテーマ：サビの反復の印象づけ）。テーマ＝{背景のプリセット、パーティクルのプリセット}（`core/themes.py`、12 種）。
2. **行の構成**：行ごとにレイアウト・登場・保持・退場・距離の層・蓄積の有無を抽選します（JIZURA の `pickLayout/pickEnter/...` を移植。直近の重複回避と強調の補正を含む）。3D 文字の行は、3D 専用のレイアウトにも重みを付けます。
3. **ギミック**（`parts/gimmicks.plan`。段階 5。行の構成の後に動く）：行の文字列に同義語辞書のキーワードが含まれれば、ギミックの候補にします（§8.3）。候補の行は「35% ＋ 65% × 物体の多さ」の確率で、強調の行は必ず出します。セクションごとの上限は「3 × (0.4 ＋ 物体の多さ)」（既定で 3）です。行の「ステージの物体」で指定した行は、確率と上限に関係なく出します。
4. **パーティクル**（`world.plan_particles`）：テーマのプリセットから、強さに応じて 1〜3 個をセクションの範囲に置きます。行の `!`（インパクト）と強調（装飾の強さに応じた確率）で、文字の位置に「きらめきの破裂」を足します（文字が出た後に始める：仕様書 §7.6）。行の「この行のパーティクル」は、その行の表示中だけ足します。発生の多さは音量の包絡から作ります（1 秒ごと、0.45〜1.0。盛り上がりで増える）。
5. **背景の切り替え**（`world.plan_world`）：セクションの境目で、テーマの背景から選んで切り替えます（テーマが同じなら、「背景の切り替え」の強さに応じて切り替えないこともある）。トランジションは雰囲気の好みから選び、境目を中心に置きます。行の「この行からの背景」は、その行の開始から切り替えます。トランジションは重ならないよう、前のものが終わるまで後ろにずらします。セクションと行の配色は、その時刻の背景に対して、スタイルの配色を補正して決めます（`styles.palette`。文字はコントラスト比 3 以上、強調は 2.4 以上）。基準の色は、山並み・街並みのシルエットがあればその色（目の高さの文字のすぐ後ろにあるため）、無ければ空の地平線の色です（`backgrounds.backdrop`）。
6. **イベント**（`world.plan_events`）：インパクトの行とサビの始まりにフラッシュ（ドームの白飛び。演出の「フラッシュ」が入のとき）、ポップ系の雰囲気のサビでは拍の脈動（明るさ 6%）。強いフラッシュ（量 0.3 以上。ホワイトアウト・暗転のトランジションを含む）は 0.4 秒以上離し、1 秒あたり 3 回以下にします（仕様書 §7.5）。
7. **視線の誘導**：文字のベイクの後に、行ごとに誘導を付けるかを決めます（§8.4）。乱数は文字の構成と同じ段階を使うので、パーティクルだけを振り直しても変わりません。

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
- レイアウトの部品は、次の属性を持ちます（段階 2 で確定）。
  - `big`：空間を大きく使う（円弧・螺旋・散らし・立ち並ぶ・迫ってくる・回る立方体）。`anchored`：プランナーの指定した位置（方位・仰角）に従う。`keepable`：セクションの終わりまで残る行に使える（見上げは、割り当てた位置より上へずれるので使えない）。`fixed_distance`：距離の層を固定する。`enter_ok`・`exit_ok`：組み合わせられる動き。
  - `group_motion(ctx, params, placement, t)`：行全体を動かす（迫ってくる・回る立方体）。`shown(ctx, params, placement)`：文字ごとに表示する時間帯を狭める（回る立方体は、見せている面の文字だけを表示する）。
- 文字の座標系：行と文字のローカル座標は「x＝文字の並び、z＝上、-y＝観客の方（文字の表面）」です。動きの `Delta` の位置は、文字ごとの静止時の向きを基準にした座標で表します（円弧上の文字でも「奥へ」が観客から遠ざかる向きになる）。
- 「分解→集合」「爆散」は、段階 2 では文字単位で動かします（字形の部品への分解は後の段階。改善メモ）。「粒子から集まる」「粒になって散る」の Blender のプレビューは、文字の動き・縮小・透明度による近似です（Unity では ParticleSystem で表現する）。

### 5.7 ベイク（`bake.py`）

1. ノードを作ります：行ごとに `group`、文字ごとに `glyph`（3D 文字なら `glyph3d` のメッシュ）。蓄積モードで、モバイル最適化 ON のときは `line_mesh` も作ります（§11.3）。
2. 文字ごとに、登場〜退場の範囲の時刻配列（既定 30Hz。コマ打ちのときはその間隔）を作り、静止姿勢に `Delta` を合成して、`location/rotation/scale/color` を計算します（numpy でベクトル化）。
3. `active` は表示の切り替わりの時刻だけを持ちます。
4. **間引き**：線形補間で許容誤差（位置 1 mm、回転 0.2°、拡大率 0.5%、色 1/255）を超えないように、Ramer–Douglas–Peucker 法でキーを減らします。
5. ドーム・パーティクル・ギミックも、同じトラックの形にします。

- 時刻の窓：登場は部品の `windows()`（既定は 0.04 秒ずつずらす。「歌に合わせて 1 文字ずつポップ」と「タイプ」は文字単位の時刻）、退場は行の終わりから逆算し、最後の文字が行の終わりに消え終わるようにします。保持は、登場が終わってからの経過時間を受け取ります。
- `active` のトラックは「0 秒で非表示 → 登場で表示 → 退場の終わりで非表示」の一定補間です。
- 目から 0.6 m より内側に入る位置は、目からの方向に沿って外へ押し出します（世界座標で判定し、行のローカル座標に戻す）。
- プランナー（§5.5）：行ごとの乱数は `Rng(h(seed, 2, 行番号 + 1))`（段階 2 ＝文字の構成）。直近 6 行の重複を避ける重み（直前 2 行は ×0.2、それ以前は ×0.6。JIZURA の `novelty`）と、強調・3D 文字の補正を掛けて選びます。「セクションの終わりまで残る」行は、観客の左右（方位 ±62°・±105°、仰角 0°・22°・8°）の 6 つの位置を順に使い、正面を空けます。残る行がある間は、空間を大きく使うレイアウトを選びません。表示の終わりは、次の行の開始か、`開始 + max(3.6, 文字数 × 0.5 + 1.2)` 秒の早いほうです（JIZURA の `visEnd`）。
- 残る行の移動（`LinePlan.glide`）：残る行は、まず正面（方位 0°・仰角 0°）に出て、次の行の開始の 0.9 秒前から 1.0 秒かけて、割り当てた位置へ移ります。ベイクでは、行の静止姿勢を割り当てた位置で作り、目を中心にした回転 `facing(方位(t), 仰角(t)) ⊗ facing(方位, 仰角)⁻¹` を行の親に掛けます。方位は in-out sine、仰角は前半で先に合わせます（奥の位置へ行く行が、手前の 2 つの位置の間を通るように）。セクションの最後に残る行は、位置を使わず正面のまま残します。
- 残る行には、床のレイアウト（位置の仰角を無視し、同じ側の 2 つの位置が床で重なる）を使いません。退場は、その場で消える種類（フェード・粒になって散る・奥へ飛び去る・縮小）に限ります。
- キーの時刻は 0.1 ms 単位にそろえてから重複を除きます。近すぎる時刻は、float32 のフレーム番号で同じ値になり、Blender が 2 つのキーを 1 つにまとめてしまうためです（その手前の区間の位置がずれた）。

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
- キャッシュ：キーは `(フォントのパス, 文字, 2D/3D, 厚み, ベベル, 解像度, 最適化の有無)` です。メッシュのデータブロックを共有します。キーはメッシュのカスタムプロパティ `llb_glyph` に保存し、.blend を開き直しても再利用します。
- 向き：字形は XY 平面（表面 +Z）で作られるので、X 軸まわりに 90° 回して XZ 平面（表面 -Y）にそろえます。行の座標系（§5.6）と同じ向きです。
- 字形の無い文字：役割のフォント → 本文 → 他の役割の順に探し、どれにも無い文字は作りません（豆腐を出さない）。
- 部品分解：2D 面を bmesh で連結成分（島）に分け、島ごとのメッシュ（原点＝島の重心）を作ります。分解→集合・爆散の動きで使います。
- 縦書き：送りは `vmtx`。長音・括弧などは JIZURA の `VERT_ROTATE` に従って 90° 回し、小書きの文字はずらします。

---

## 7. 空間配置と動き

### 7.1 座標と大きさ

- 観客点＝原点、目線＝(0, 0, `eye_height`)、正面＝+Y。
- 距離の層の既定：近景 1.2 m、中景 3.5 m、遠景 8 m（行の中心までの距離）。
- 文字の大きさは**視角**で決めます。`size = 2·d·tan(θ/2)`。θ の既定は、本文 3.5°、強調 5.5°、注釈 1.2° です（段階 2 の見た目の確認で、2.5° では字幕のように小さかったため変更）。行の長さが水平の視野 70° を超える場合は、縮めるか改行します。
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
| `emitter`（sphere/sky_shell/sky_disc/floor_disc/ring/tunnel/burst）、`radius`、`height` | ShapeModule |
| `rate`、`burst`（間隔・数・速さ・寿命・`sub`） | EmissionModule（バーストは、発生源の位置のトラックとバーストの時刻） |
| `life`、`speed`、`size`、`gravity`（範囲） | MainModule（MinMaxCurve の TwoConstants） |
| `colors`（スタイルの配色の役割名）、`fade`（寿命の初めと終わりの透明度） | MainModule.startColor、ColorOverLifetime |
| `direction`、`noise`・`noise_freq`、`spin`、`size_life`、`trail`、`sub` | VelocityOverLifetime・Noise・RotationOverLifetime・SizeOverLifetime・Trails・SubEmitters |
| `blend`（add/alpha） | マテリアル |
| `max` | MainModule.maxParticles（モバイル時は比率で減らす） |
| `prewarm` | MainModule.prewarm |

- 2D のテクスチャは、`core/atlas.py` が numpy で符号付き距離から描きます（1024×1024、4×4 のタイル。15 種）。Blender のプレビューでも同じ画像を使い、Unity 出力（段階 4）では PNG にします。
- 強さ（演出の「パーティクルの量」）で、`rate` と `max` を 0.35〜1.65 倍にします。
- **閉じた式**（`state(spec, t)`）：連続の発生源の粒 i は、寿命 L_i ごとに生まれ直し、世代ごとに新しい乱数で発生位置・速度を決めます。位置＝発生位置＋速度×経過＋重力＋ノイズ（正弦の和）。発生の多さ（`intensity`）は、生まれた時刻の値で粒を間引きます。破裂は、時刻と発生位置のリストから、粒ごとに減速つきの放射で求め、寿命の終わりに `sub` の粒が弾けます。粒は目から 0.6 m より内側に入れません（§7.2）。発生源全体は、開始から 0.8 秒で現れ、終了から 1.0 秒で消えます（`envelope`）。
- プレビュー（`preview/particles.py`）：`frame_change_pre` のハンドラで、毎フレーム `state()` を計算し、発生源のメッシュに書き込みます。2D は観客の目（0, 0, 1.5）の方を向く四角形（軌跡のある粒は速度の向きに伸ばす）、3D は形状のメッシュです。頂点数は「連続の粒の数＋破裂の最大同時数」で固定し、消えた粒は大きさ 0 にします。色は頂点の色属性 `llb_col` に書きます。Unity は ParticleSystem が自分で計算するので、見た目は似ていても同じにはなりません。

### 8.2 背景ドーム

- メッシュ：アイコスフィア（細分化 3、半径 60 m）の面を内側に向けたもの（`core/meshes.dome`）。中心は目の高さ。UV は使わず、シェーダーが方向（オブジェクト座標を正規化）から色を求めます（パノラマ画像も方向から引く）。
- シェーダーは不透明・`Cull Front`・**`ZWrite On`** にします。Unity は不透明物の後に、深度が最も遠いままの画素へ Skybox を描きます。そのため、深度を書かないドームは Skybox に上書きされて見えなくなります（試作 S0-07 で確認）。
- シェーダーのパラメータ（A と B の2組＋進行度）

| パラメータ | 内容 |
|---|---|
| `modeA/modeB` | 0 単色 / 1 上下グラデ / 2 帯グラデ / 3 模様 / 4 画像 |
| `top/horizon/bottom`（A・B 各組） | グラデーションの 3 色。グラデは地平線からの高さ h について √|h| で補間 |
| `ink`、`bands`、`pattern`、`pscale`（A・B 各組） | 模様の線の色、帯の数、模様（0 同心円 / 1 緯度経度の格子 / 2 水玉）、模様の細かさ |
| `next` | 次に見せる組（1＝B、0＝A） |
| `progress` | 切り替えの進行度。B へは 0→1、A へは 1→0 と動かすので、切り替えの開始で値が飛ばない |
| `trans` | 0 クロスフェード / 1 上から / 2 下から / 3 横から / 4 正面からのリング / 5 ディゾルブ（ノイズ） |
| `flash`、`flash_color` | 白飛び・暗転の量と色（ホワイトアウト・暗転のトランジションとフラッシュ） |
| `bright` | 明るさの倍率（拍の脈動） |
| `cue_dir`、`cue_amount` | 視線の誘導：その方向を中心に明るさを足す（§8.4） |

- B の重み：q = progress（next=1）または 1−progress（next=0）、m = 種類ごとのマスク（クロスフェードは q、ワイプ・リング・ディゾルブは、掃引の座標 s が q で動く境目より手前か。境界のぼかし幅 0.06）、w = m（next=1）または 1−m（next=0）。色 = mix(A, B, w) → フラッシュ → 明るさ → 誘導の光。
- 切り替えの手順：次の背景を、見えていない側の組に、切り替えの開始の時刻に書き（一定補間のキー）、`next` をその組に変え、`progress` を 1.0〜1.8 秒で動かします（`core/bake_world.dome`）。A へ B をコピーする手順は要りません。
- 背景のプリセット 14 種（`core/parts/backgrounds.py`）：朝・昼・夕焼け・夜・夜明け・星空（時間帯）、海の中、深い宇宙、帯の夕暮れ、同心円・格子・水玉（模様。色はスタイルから）、スタイルの色、パノラマ画像（画像を指定したときだけ）。トランジション 8 種：クロスフェード、ホワイトアウト、暗転、上から・下から・横からのワイプ、広がるリング、ディゾルブ。
- Blender のプレビュー：同じロジックのシェーダーノードを組みます（1 組分をノードグループ `LLB_DomeSlot` にする）。パラメータは、マテリアルの中の `llb_<名前>` の Value / RGB ノードの値を、ノードツリーのアクションで動かします。オブジェクトのカスタムプロパティを Attribute ノード（Object）で読む方式は、Blender 5.0 の EEVEE で、1 つのマテリアルが読める属性の数を超えてドームが黒くなったため使いません。
- 遠景オブジェクト（`core/meshes.py`）：月・太陽（円盤。目から 50 m、目の方を向く）・山並み・街並みのシルエット（観客を囲む帯）・水面（足元より 0.6 m 下の円盤）。unlit で、その背景のトランジションに合わせて透明度で現れ・消えます。プレビューのマテリアル `LLB_Far` は、深度を書く不透明の描き方（Dithered）にします（透明度はディザで表す）。半透明（Blended）の物体は原点の距離で並べて描かれ、山並み・街並みの帯は原点が観客の足元にあるため、文字の上に描かれていました。Unity（段階 4）でも、遠景は文字より先に描く描画順（不透明、またはそれに近いキュー）にします。

### 8.3 ギミック

- **物体の解決**（仕様書 §8.3.1、`parts/gimmicks.plan`）：行のキーワードのタグについて、次の順で決めます。
  1. ユーザーのタグ索引（`preview/gimmick_assets.py`。`Settings.user_assets`）
  2. 内蔵の基本形の表（`core/gimmick_shapes.SHAPES`。25 種。numpy で作るので、プレビューと出力で同じ形になる）
  3. 紋章（辞書にあるが基本形も資産も無いタグ、または行の設定が「キーワードの紋章」）
- **同義語辞書**（`core/synonyms.py`）：`{タグ: (語, ...)}` の形にします。照合は、歌詞とタグを NFKC・小文字・カタカナ→ひらがなにそろえてから、長い語を優先して部分一致で行います。英字の語は単語の境界で区切ります（starlight は star にしない）。部分一致の誤りを防ぐため、語を含むだけの言葉（ほしい・はなし・言葉・月曜など）の一覧 `STOP` を先に取り除きます。利用者の追加分は、プリファレンスの「追加のキーワード」に `cat=ミケ,タマ; fox=きつね` の形で書きます。利用者のタグも `canonical` で辞書のタグにそろえるので、`猫` でも `cat` でも一致します。
- **タグ索引**：「ライブラリを更新」で、指定したアセットライブラリの .blend をすべて調べます。調べ方は `bpy.data.libraries.load(path, link=True, assets_only=True)` でオブジェクトを一時的にリンクし、`asset_data.tags` を読んで、すぐライブラリを外す、です。結果（ファイル・名前・タグ）を、Extension のユーザーディレクトリの JSON に保存します。100 個で 0.02 秒です（試作 S0-10）。後始末はライブラリを外すだけにし、`bpy.data.orphans_purge()` は使いません（利用者の未使用データまで消すため）。利用者のファイルが既に同じライブラリをリンクしている場合は、ライブラリを外しません。
- **取り込みと正規化**（`gimmick_assets.mesh`）：使うときに append し、モディファイアを適用した評価済みのメッシュにします。高さ 1・底面の中心が原点になるようにそろえ、ノードの拡大率で大きさを決めます。正面は Blender の標準の -Y とみなします（回転はしません）。マテリアルのベースカラーとそのテクスチャは、頂点の色（属性 `llb_col`）に写します。UV を出力しないので、Unity 側は全物体で同じシェーダーになります。モバイル最適化では 1000 三角形まで減面します。一時的に読み込んだオブジェクト・マテリアル・Library は取り除きます。
- **配置**：行のアンカーの方位から左右に 38〜58° ずらした、半径 4 m の位置に置きます（同じセクションでは左右を交互に）。正面（-Y）を観客に向けます。空中の形（星・月など）は高さ 2.3 m、それ以外は床に置きます。大きさは視角 20° を基準に、形ごとの倍率を掛けます。滞在は行の表示に合わせ、2.5〜6 秒＋ 0.3 秒です。
- **出し方**（`core/bake_gimmick.py`）：ギミックはグループのノードと、見える部品の子ノードです。グループの `location`・`rotation`・`scale` で出し方を表し、部品ごとに `active` を持ちます（Blender は親を隠しても子を隠さないため）。

| 出し方 | 動き |
|---|---|
| 床から生える | Z 拡大率 0 → 1（少し行き過ぎる）と、位置を少し下から |
| 空から降る | 高さ +5 m から落ちて、2 回小さく弾む |
| 壁から出る | 2.5 m 奥から押し出され、拡大率 0 → 1 |
| ポップ | 拡大率 0 → 1（行き過ぎる） |
| ひっくり返る | 円板の子として物体を載せ、グループを X 軸で 180° 回す（裏側にあった物体が上に来る） |
| 箱が開く | 4 枚の壁（下の辺が蝶番）を 100° 倒し、蓋を持ち上げて消す。物体は最初から中にある |
| 溶けて消える | `color` の透明度でディゾルブ（現れるときも同じ）。他の出し方の退場は、拡大率を 0.35 秒で 0 にする |

  - 空中の形には、床が要る「床から」「ひっくり返る」「箱」と「空から」は自動では選びません。行で指定した場合は、床に置きます。
  - 現れた後は、ゆっくり左右に揺れ（±10°、周期 4 秒）、空中の形は上下にも揺れます。
- **ディゾルブ**：`color` の透明度を流用します。ノイズが `1 - alpha` より大きい部分を残します（`LLB_Gimmick.shader` は `clip`、プレビューの `LLB_Gimmick` は Noise Texture と Dithered）。アニメーションのプロパティを増やさずに済みます。紋章の文字は `text` マテリアルなので、ディゾルブではなく透明度で消えます。
- **紋章**：単語の文字を、既存の `glyph3d` のノード（厚み 0.2、ベベル 0.015）としてグループの下に並べ、床に円板の台座を置きます。単語は、行の「紋章の単語」、キーワード、強調の語、最も長い区切りの順に決めます。
- **スペクトラムバー**：24 本を半径 4.2 m の円に並べ、`audio.py` のスペクトラムから拡大率の Z のトラックを作ります（20 Hz、速く上がってゆっくり下がる。間引きつき）。正面が低音、真後ろが高音で左右対称です。「演出」パネルで、なし・サビだけ（既定）・曲全体を選びます。色はセクションの強調の色です。曲が無ければ作りません。

### 8.4 視線の誘導（`core/guide.py`、仕様書 §7.6）

- **判定**：行ごとに、推定した視線の方向と行の方向の角度を求めます。
  - 推定した視線：直前の行の文字の重心の方向（新しい行の最初の文字が出る 0.8 秒前の位置。ベイク済みのトラックから求める）。直前に表示中の行が無ければ正面。
  - 行の方向：最初の文字が出た時刻の、文字の重心の方向。
  - 角度が 30° 以上なら誘導を付けます。行の設定が「あり」なら角度に関係なく付け、「なし」なら付けません。
  - 行の設定が「あり」で角度が 45° 未満のときは、光の筋が短すぎて見えないので、出発点を行から 45° 離れた真横にします（`_start_at`。推定した視線の側。視線が行の上なら行の番号で左右を交互に）。上下に振らないのは、床の下から出さないためです。
- **光の筋**：粒を 3〜6 個（強さに応じる）、推定した視線の位置から行の位置へ、上へふくらむ弧（大円＋仰角のふくらみ 8°）に沿って動かします。時刻は `t_hit − lead → t_hit`（in-out sine。`lead` は移動の角度に比例して 0.7〜1.2 秒。Udon 同期を付ける出力では、実際の視線の角度が分からないので常に 1.5 秒＝最長の 1.2 秒＋視線の位置に留まる 0.3 秒）、粒ごとに 0.03 秒ずつ遅らせ（間を詰めて、点の列でなく尾を引く 1 本の筋に見せる）、後ろの粒ほど小さく薄くします。到着後 0.25 秒で縮んで消えます。粒の距離は、行の距離へ向けて補間します。
  - BakedScene では、誘導 1 回分の親（`guide<番号>`、kind `group`、目の位置）の子に、粒ごとのノード（kind `mote`、メッシュ `orb`。位置は目からの相対）を置き、`location`・`scale`・`color`・`active` のトラックにします。Blender のプレビューでは、中心ほど明るい光の玉（Layer Weight の Facing で縁を消す加算のマテリアル `LLB_Glow`）で表します。Unity では、トレイルを付けた 1 つの粒にすると、より滑らかな筋になります（段階 4 で検討）。
- **予兆の灯り**：親の子として、行の重心の少し奥（0.3 m）に、大きめの光の玉（半径＝距離 × 0.06）を置き、`t_hit − 0.4` から明るくして（最大の透明度 0.55）、`t_hit + 0.3` までに消します。
- **ドームに差す光**：視線から 90° を超える行では、ドームの `cue_dir` をその方向にし、`cue_amount` を `t_hit − 0.7 → t_hit` で 1 に上げ、`t_hit + 0.8` までに戻します。シェーダーは、方向との内積の 6 乗に比例して、暖かい白（1, 0.95, 0.85）× 0.12 × 量を足します（暗い夜空でも分かるよう、掛け算ではなく足し算にした）。点滅ではないので、フラッシュの回数には数えません。
- **色**：文字の色（強調の行は強調の色）のうち明るいほう。明るさが 0.3 未満なら白へ 75% 寄せます（昼の空の上の暗い文字色では、加算の光が見えなかった）。
- **全体の演出との分離**：行に結び付いたバースト（`!`・強調）の開始を、`t_hit` 以降にずらします。誘導のノードは `category = "guide"` にし、パーティクルの振り直しの対象にしません。
- 連続して誘導が付く場合も、1 秒あたり 2 回までにします（間隔の狭いものは、角度の大きいほうを残す）。
- Udon 同期を付けた Prefab では、粒の位置を Udon が観客ごとの実際の視線から計算し直します。すでに行の方を見ている観客には、親を非表示にします（§10.7）。

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
    textures/particles_atlas.png, panorama.<拡張子>
    audio/<曲ファイル>
    fonts/<フォント>           # TMP 変換が ON のときだけ。フォントアセットを作った後に Unity 側が削除する（§10.8）
    _llb_build.pending        # 未組み立ての印（最後に書く。組み立て後に削除）
    _llb_udon.pending         # Unity 側が置く：Udon のスクリプトのコンパイル後に組み立て直す印（§10.7）
    FontAssets/               # Unity 側が生成：TMP のフォントアセット（組み立て直しで使い回す）
    Generated/                # Unity 側が生成：Meshes.asset、Materials/、Clips/、<曲名>.playable、<曲名>.prefab
```

- `Editor/` と `Runtime/` は、アドオンの版より古い場合だけ上書きします（各フォルダの `version.txt` の整数で判定。テンプレートを変えたら上げる）。利用者が足したファイルは残します。
- 出力の前に `Songs/<曲名>/` の中身を確認し、`Generated/` が既にあれば上書きの確認ダイアログを出します（仕様書 §9.2-4）。
- 印のファイル名は `_llb_build.pending` にします（`_pending.llb` ではない）。テスト用プロジェクトに残る段階 0 の試作の自動組み立てが `_pending.llb` を監視していて、本実装の出力を別のデータとして組み立てようとするため。
- 出力の前に、Unity が見つかること・プロジェクトであること（`Assets` と `ProjectSettings`）・Timeline パッケージがあること（`Packages/manifest.json` か `packages-lock.json`）を確かめます。無ければエラーダイアログを出し、何も書きません。Timeline は組み立てのスクリプトのコンパイルに要ります（空のプロジェクトには入っていない。VRChat のワールドには入っている）。プロジェクトの設定は書き換えません。TMP 変換が ON なら TMP パッケージ（`com.unity.textmeshpro`）も確かめます。Udon 同期が ON で `com.vrchat.worlds` が無い場合は、出力の後に警告を出します（同期なしで組み立てる）。

### 9.2 manifest（JSON）

Unity の `JsonUtility` で読めるように、辞書と入れ子の配列は使いません。数値の配列は平らにします。

```json
{
  "format": "llb-manifest", "version": 1, "generator": "LyricLiveBuilderForBlender 0.1.0",
  "song": { "title": "", "artist": "", "audio": "audio/song.wav", "duration": 215.3, "bpm": 128.0 },
  "options": { "materialMode": "VRCHAT", "panorama": "" },
  "sections": [ { "index": 0, "label": "Intro", "kind": "intro", "start": 0.0, "end": 12.4 } ],
  "meshes": [ { "key": "glyph2d|body|空", "offset": 0, "length": 5120 } ],
  "materials": [ { "key": "text_f5eeeaff", "shader": "text", "color": [0.96,0.93,0.92,1], "params": [] },
                 { "key": "dome", "shader": "dome", "color": [1,1,1,1], "params": [ { "name": "_TopA", "values": [0.1,0.2,0.4] } ] } ],
  "nodes": [ { "id": 12, "name": "空", "parent": 11, "category": "text", "kind": "glyph", "mesh": "glyph2d|body|空",
               "material": "text_f5eeeaff", "p": [0,0,0], "r": [0,0,0,1], "s": [1,1,1], "active": false, "particles": "" } ],
  "clips": [ { "section": 0, "category": "text",
               "curves": [ { "node": 12, "type": "Transform", "attr": "m_LocalScale", "fields": ["x","y","z"],
                             "interp": 0, "times": [0.0, 0.1], "values": [0,0,0, 1,1,1] } ] } ]
}
```

- `nodes[].p/r/s` と `curves[].values` は、**Unity の座標系に変換済み**です（§9.4）。色は sRGB です。
- 曲線は、Unity の `EditorCurveBinding` の型・属性・成分の名前まで Python 側で決めます（`export_unity/manifest.binding`）。C# は文字列をつなぐだけです。
- `parent` が −1 のノードは、分類のルート（Text・Particles・Background・Gimmicks）の直下に置きます。視線の誘導は Text に入れます。同じ親の下の名前は一意にします（アニメーションのパスが名前なので。1 行に同じ字が 2 つある場合など）。
- パーティクルの系は、ノードの `particles` に Unity 向けの説明の JSON 文字列を入れます（`export_unity/particles_unity.py`。入れ子の配列は使わない）。系が 2 つになる発生源（上下 2 段の輪）は、子のノードに分けます。破裂（花火・きらめき）は、破裂ごとに子のノード（ループしない系）を作り、その時刻に表示します。
- `clips` は §10.5 の規則で、セクション × 分類に切り分けて出力します。

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

- 法線を必ず書きます。3D の文字と 3D のパーティクルの形は、三角形ごとに頂点を分けて面の法線にします（側面を暗くするため）。2D の文字・ドーム・光の玉は頂点を共有し、面の法線の平均にします。UV・色・シェイプキーは段階 6 以降で使います（読み込みは対応済み）。

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

- `subprocess.Popen` で起動し、モーダルオペレーターのタイマー（0.5 秒）で終了とログを確認します（Blender の画面を止めない。`Esc` で中止）。
- ログの `[LLB]` で始まる行を、「Unity 出力」パネルの状態に表示します。終了コードが 0 以外ならエラーダイアログを出し、ログのパスを示します。
- プロジェクトが開いている場合（§9.5 のロック判定）は起動せず、「Unity に切り替えると自動で組み立てる」と表示して終わります（`LLBAutoBuild`）。

---

## 10. Unity 側（`templates/`）

### 10.1 ファイル

| ファイル | 役割 |
|---|---|
| `Editor/LLBBuilder.cs` | 入口。`BuildFromCommandLine()`、`Build(songFolder)`、メニュー `Tools/LyricLive/Rebuild All Songs` |
| `Editor/LLBAutoBuild.cs` | `[InitializeOnLoad]` と `AssetPostprocessor`。`_llb_build.pending` を見つけたら `EditorApplication.delayCall` で組み立てる |
| `Editor/LLBManifest.cs` | manifest のクラス（`[Serializable]`） |
| `Editor/LLBMeshReader.cs` | `meshes.bin` → `Mesh`（.asset）。シェイプキーは `AddBlendShapeFrame` |
| `Editor/LLBMaterialFactory.cs` | マテリアルの生成（VRChat の Mobile シェーダー／同梱シェーダー／標準。シェーダーが見つからない場合の代替） |
| `Runtime/Shaders/LLB_Gimmick.shader` | ステージの物体。不透明、固定の光の陰影、`_Color` × 頂点の色、`_Color.a` でディゾルブ |
| `Editor/LLBParticleFactory.cs` | プリセット → ParticleSystem の各モジュール |
| `Editor/LLBAnimationFactory.cs` | `clips` → `AnimationClip`（`AnimationUtility.SetEditorCurve`） |
| `Editor/LLBTimelineFactory.cs` | `TimelineAsset`・トラック・クリップ・バインディング・マーカー |
| `Editor/LLBTextMeshProFactory.cs` | TMP のフォントアセット（静的アトラス）と、文字ごとの TMP（§10.8）。TMP が無いプロジェクトでは空の実装になる（`#if LLB_TMP`） |
| `Editor/LLBUdonSyncFactory.cs` | 開始ボタンと Udon 同期の部品（§10.7）。UdonSharp の API はリフレクションで呼ぶ |
| `Editor/LyricLive.Editor.asmdef` | Timeline・TMP を参照するエディタ用アセンブリ。`versionDefines` で TMP がある場合だけ `LLB_TMP` を定義する |
| `Runtime/Shaders/LLB_Text.shader` | 文字。色と透明度、視線に対して斜めの面を暗くする |
| `Runtime/Shaders/LLB_TextVC.shader` | 行メッシュ（§11.3）。`LLB_Text` に頂点の色を掛ける |
| `Runtime/Shaders/LLB_Far.shader` | 遠景。キュー 2900（ドームの後、文字の前に描く） |
| `Runtime/Shaders/LLB_Glow.shader` | 視線の誘導の光の玉（加算、縁で消える） |
| `Runtime/Shaders/LLB_Particle.shader` | パーティクル。アトラス × 頂点の色 × `_Color`（発生源の現れ・消え）。加算と半透明は `_SrcBlend/_DstBlend` |
| `Runtime/Shaders/LLB_Dome.shader` | §8.2 のドーム（Blender のプレビューのノードと同じ式） |
| `Runtime/Udon/LLBSync.cs.txt` | 同期スクリプトの元（拡張子を変えて、コンパイルされないように置く。UdonSharp がある場合だけ `LLBSync.cs` にコピーする） |

### 10.2 組み立ての手順（`LLBBuilder.Build`）

1. manifest を読み、版を確認する。
2. `Generated/` を作り直す（以前の生成物を削除）。
3. メッシュ → マテリアル → テクスチャの取り込み設定（アトラスは Clamp・ミップマップあり）。
4. 階層を作る（ルート → 分類 → ノード）。分類のルートに Animator（Controller 無し）を付ける。ノードの表示・非表示は manifest の `active` の初期値（文字・遠景・パーティクルは非表示、行のグループ・ドームは表示）。組み立ては `EditorSceneManager.NewPreviewScene()` の中で行い、開いているシーンを汚さない。
5. パーティクルの生成。
6. AnimationClip の生成（§10.5）。
7. Timeline の生成（§10.6）。ルートに PlayableDirector と AudioSource を付け、バインドする。
8. オプション：TMP 変換、Udon 同期。
9. Prefab として保存し、`_llb_build.pending` を削除する。`[LLB] done` をログに出す。

組み立ては、作業用の一時オブジェクトだけで行い、開いているシーンのオブジェクトには触れません。シーンに置いた Prefab のインスタンスは、Prefab の上書きで自動的に更新されます（S0-03 の試作で、名前でシーンを検索して削除する処理が、シーンに置いたインスタンスまで消した）。

### 10.3 マテリアルの対応

| 仕様上の種類 | VRCHAT モード | 代替（シェーダーが見つからない場合） | STANDARD モード |
|---|---|---|---|
| text | `LyricLive/Text` | `Unlit/Transparent` → `Unlit/Color` | 同左 |
| far | `LyricLive/Far` | `Unlit/Transparent` → `Unlit/Color` | 同左 |
| glow | `LyricLive/Glow` | `Particles/Standard Unlit` | 同左 |
| particle（加算・半透明・3D） | `LyricLive/Particle` | `Particles/Standard Unlit` | 同左 |
| dome | `LyricLive/Dome` | `Unlit/Color` | 同左 |
| gimmick | `LyricLive/Gimmick` | `Unlit/Color` | 同左 |

- 段階 4 では、どちらのモードも同梱シェーダーを使います（試作 S0-07 で、PC・Quest・iOS での表示を確認済み）。同梱シェーダーが見つからない場合は、表の代わりのシェーダーにして `[LLB][WARN]` を出します。lit・MatCap（仕様書 §7.2）は改善メモ #12。
- 色は `SetColor` に sRGB の値で渡します（Linear のプロジェクトでも、Unity が線形に直す）。

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

| `dome:<名前>` | `typeof(MeshRenderer)`, `material._TopA.r/g/b` など（色は sRGB、`_CueDir` は `.x/.y/.z`、数値は成分なし） |

- 補間：linear はキーの接線を前後の区間の傾きに、constant は接線を無限大（階段）にします。`active` は常に constant。まとめて `AnimationUtility.SetEditorCurves` で書きます。
- 発生源の `color` は `ParticleSystemRenderer` の `material._Color`（現れ・消え）、`emit_rate` は `ParticleSystem` の `EmissionModule.rateOverTime.scalar` です。

### 10.5 クリップの分割規則

- クリップ＝「セクション × 分類」。範囲は `[section.start, section.end)` で、クリップ内の時刻は 0 から始めます。
- **クリップは自己完結させます。** Timeline の Animation Track は、そのとき再生中のクリップに含まれないプロパティを既定値に戻します。そのため、各クリップには、そのセクションで動く・見えるノードのすべてのプロパティを、開始時刻の値から入れます。
- セクションの境目をまたぐ要素（退場の途中の文字・続いている背景・パーティクル）は、両方のクリップに含め、境目の時刻の値をそろえます。
- 既定値（Prefab に保存される状態）は「すべて非表示・静止姿勢」です。
- 実装：セクション [s0, s1) の中で一度でも表示されるノードの全トラックを、s0 の値（補間で求める）＋区間内のキー＋s1 の値（linear のみ）で切り出し、時刻を 0 からにします。何も動かない分類のクリップにも、ルートの拡大率の一定の曲線を 1 本入れて、クリップの長さをセクションに合わせます。

### 10.6 Timeline

| トラック | 種類 | バインド | クリップ |
|---|---|---|---|
| Audio | AudioTrack | ルートの AudioSource | 曲 1 本 |
| Text | AnimationTrack | `Text` の Animator | セクションごと |
| Particles | AnimationTrack | `Particles` の Animator | セクションごと |
| Background | AnimationTrack | `Background` の Animator | セクションごと |
| Gimmicks | AnimationTrack | `Gimmicks` の Animator | セクションごと |

- クリップ名：`<2桁の番号>_<セクション名>_<分類>`（例：`03_Chorus_Text`）。AnimationClip のアセット名も同じにします（`Generated/Clips/`）。
- PlayableDirector：`playOnAwake = true`（Udon 同期を付けた場合は `false`。開始ボタンで再生する）、`extrapolationMode = Hold`（最後の状態を保つ。クリップの後の外挿は API で設定できないため、ディレクターで保つ）、`timeUpdateMode = DSPClock`（曲の時計に合わせる）。
- マーカーのトラック（セクション名・行の目印）は、段階 4 では作りません（改善メモ #16）。
- 曲は `CompressedInMemory`・Vorbis（品質 0.7）で取り込みます（4 分の曲を読み込み時に展開すると、Quest で数十 MB になるため）。

### 10.7 Udon 同期（オプション）

- UdonSharp が入っているかは、型 `UdonSharp.UdonSharpBehaviour` の有無で判定します。無ければ `[LLB][WARN]` を出し、同期を付けずに組み立てます（`playOnAwake = true` のまま）。Blender 側も、出力の後に `com.vrchat.worlds` が無ければ警告を出します。
- 同期のスクリプトは全曲で共有の `Runtime/Udon/LLBSync.cs` です（曲ごとの値は部品のフィールドに入れるので、曲ごとのスクリプトは不要）。
- 手順（スクリプトのコンパイルが要るので、2 段階で行います）
  1. `LLBSync.cs` が無い、`LLBSync.cs.txt` と内容が違う（アドオンの更新後）、または新しい内容のコンパイルが済んでいなければ（必要なフィールドが型に無い）、`LLBSync.cs.txt` からコピーし、Udon 同期なしで Prefab を保存して、`_llb_udon.pending` を置きます。ログに `[LLB] udon-pending` を出します。
  2. スクリプトの再読み込みの後、`LLBAutoBuild` の `InitializeOnLoad`（`ScanAll`）が `_llb_udon.pending` を見つけて組み立て直します（`AssetPostprocessor` では拾わない。再読み込みの前に動いてしまうため）。バッチモードでは、Blender 側が `[LLB] udon-pending` を見て、Unity をもう一度実行します。
- U# の部品の付け方（試作 S0-11 で確立）：`UdonSharpProgramAsset` を `ScriptableObject.CreateInstance` で作って `sourceCsScript` を設定・保存 → `UdonSharpProgramAsset.CompileAllCsPrograms(true, false)` → `UdonSharpEditor.UdonSharpUndo.AddComponent(GameObject, Type)` → フィールドを設定して `UdonSharpEditorUtility.CopyProxyToUdon` で反映。U# の版の差を吸収し、U# の無いプロジェクトでもコンパイルできるように、これらはリフレクションで呼びます。
  - 型は `MonoScript.GetClass()` で取ります。U# は同じクラスを自分のアセンブリ（`UdonSharpRoslynCompileAssembly<n>`）にもコンパイルするため、名前で型を探すと別の型が見つかります。
  - プログラムのコンパイルが終わっていない場合（`CopyProxyToUdon` が「outdated script version」で失敗する）は、手順 1 と同じく保留にして、再読み込みの後に組み立て直します。
- 開始ボタン：ルートの子の立方体 `LLB_StartButton`（観客の後ろ、`(0, 1, -1.2)`、0.2 m）。押すと（`Interact`）押した人がオーナーになり、再生と停止を切り替えます。
- 同期の内容：オーナーが同期変数 `startServerTime`（`Networking.GetServerTimeInSeconds()`）と `playing` を送る → 各クライアントは `director.time = now - startServerTime` にして `Play()` します。後から入室した人も、受信時に同じ計算で再生位置を合わせます。Udon からは再生速度を変えられないので、ずれが 0.2 秒を超えたときだけ `time` を設定し直します。
- **視線に合わせた誘導**：誘導 1 回分の粒と光の玉は、親（`guide<番号>`）の子にします（§8.4）。manifest の `guides`（親のノード・`tOn`・`tHit`・行の位置 `target`・粒の数 `motes`。Unity の座標）を、部品の配列に入れます。
  - 各クライアントは、`tOn` の時刻に頭の位置と向き（`GetTrackingData(Head)`）を読みます。ステージの目の位置ではなく、観客の実際の頭の位置を基準にします。行との角度が 30° 未満なら、その誘導の親を非表示にします（もう見ている）。行の設定が「あり」でも同じです。
  - それ以外は、そのときの頭の向きを出発の方向として覚え、`LateUpdate` で毎フレーム、粒の位置を「出発の方向 → 行」の弧（§8.4 と同じ in-out sine・遅れ・8° のふくらみ）の上に置きます。170° を超える場合は、真上を通します。出発の時刻は `tHit − lerp(0.7, 1.2, 角度 / 180)` で、それまで粒は視線の位置に留まります（焼き込みの表示は `tHit − 1.5` から）。距離は頭から行までの距離で、顔に近づきすぎないよう、出発の距離は 1.5 m 以上にします。
  - Timeline の `active`・`color`・`scale` はそのまま使います。粒の `location` の曲線も残しますが、Director は Update の後・`LateUpdate` の前に評価するので、Udon の値が勝ちます。Udon が付かなかった場合は、この曲線がそのまま代わりになります。
  - 粒の大きさは焼き込みの値のままです（ステージの目の位置から行までの距離で決まる）。
  - `tHit + 1` 秒で親を元に戻します。同期変数は使いません（観客ごとの見た目だけを変える）。

### 10.8 TextMesh Pro

- 対象：TMP 変換が ON のときの 2D 文字の行（3D 文字の行はメッシュのまま。2D の行は行メッシュ（§11.3）にしない）。TMP が無いプロジェクトでは、Blender 側が出力の前に止めます。
- Blender 側は、行で使うフォントを `<曲>/fonts/` にコピーし、manifest の `fonts`（キー・ファイル・使う文字）と、文字のノードの `tmp`（文字）・`tmpFont`（キー）を書きます。
- フォントアセット：`TMP_FontAsset.CreateFontAsset`（サンプリング 72 pt・余白 7・アトラス 2048×2048・アトラスの追加あり）で作り、歌詞で使う文字だけを `TryAddCharacters` で追加したら、`atlasPopulationMode = Static` にして、元のフォントへの参照を外します。最後にコピーしたフォントファイルを削除します（仕様書 §9.5）。
  - 外す参照は `m_SourceFontFile`・`m_SourceFontFileGUID`・**`m_SourceFontFile_EditorRef`** の 3 つです（`SerializedObject` で設定）。3 つめを外さないと、フォントファイルが依存に残ります（試作 S0-06）。
  - 保存先は `<曲>/FontAssets/`（`Generated/` は組み立てのたびに消すので使わない）。フォントファイルが無い組み立て直し（Udon の 2 段階めなど）では、作成済みのアセットを使います。`Fonts` という名前にしないのは、Windows のフォルダー名が大文字・小文字を区別せず、`fonts/` と同じフォルダーになるためです。
  - TMP の基本リソース（`Assets/TextMesh Pro`）が無いプロジェクトでは、TMP のシェーダーが無いためフォントアセットを作れません。無い場合は、`TMPro.TMP_PackageResourceImporter.ImportResources(true, false, false)` で自動的に取り込みます。
  - 作成したアトラスのテクスチャとマテリアルは、`AssetDatabase.AddObjectToAsset` でフォントアセットのサブアセットとして保存します。モバイル最適化が ON なら、マテリアルを `TextMeshPro/Mobile/Distance Field` にします。
- 文字ごとに TMP（`TextMeshPro`、1 文字、中央揃え）を作り、メッシュのノードの代わりに置きます。アニメーションのパスは同じにします（ノード名を変えない）。文字の大きさ：`fontSize` 10 の `GetPreferredValues` で 1 em の高さを測り、メッシュの文字と同じ高さになる値にします。
- 色のアニメーションは `TextMeshPro` の `m_fontColor.r/g/b/a` にします。

---

## 11. モバイル最適化（`mesh_optimizer/`）

### 11.1 公開関数（`api.py`）

```python
def optimize_text_curve(curve_obj, *, resolution=4) -> None
def retopo_flat_text_mesh(mesh, *, dissolve_angle_deg=1.0, merge_dist=1e-5, depth=0.0) -> RetopoReport
def fit_text_mesh(make_mesh, *, max_tris, resolutions=(4, 3, 2), dissolve_angle_deg=1.0, depth=0.0) -> FitReport
def extrude_flat_mesh(mesh, *, depth) -> None
def decimate(mesh, *, ratio=None, target_tris=None, planar_angle_deg=2.0) -> int
def merge_static_objects(objects, *, by_material=True) -> list
def bake_palette_material(objects, *, max_colors=64) -> PaletteResult
```

- 本体からは `fit_text_mesh` を使います（`export_unity/exporter.py`）。それ以外は、単体のアドオンとして手作業で使う関数です。
- 単体のアドオンとして入れた場合は、`ui.py` が 3D ビューのサイドバーに「Mesh Optimizer」パネルを出し、選択したオブジェクトに上の処理を行います（文字の整理・減面・まとめる（元は非表示）・パレットのマテリアル）。本体からは `ui.py` を使いません。
- 単体の zip は `blender --command extension build --source-dir lyric_live_builder/mesh_optimizer` で作ります。本体の zip には、パッケージは入りますが、`blender_manifest.toml` は入りません（`paths_exclude_pattern`）。

### 11.2 文字のリトポロジー（`retopo.py`）

参考記事の手作業を、bmesh で次のように自動化します。

1. テキストの曲線の解像度を下げてメッシュにする（§6.2）。
2. `bmesh.ops.remove_doubles(dist=1e-5)` で近接頂点を結合する。
3. `bmesh.ops.dissolve_limit(angle_limit=1°, use_dissolve_boundaries=False)` で、同一平面の三角形を多角形にまとめ、ほぼ直線上の頂点を取り除く。
4. `bmesh.ops.triangulate(quad_method='BEAUTY', ngon_method='BEAUTY')` で三角形化し直す（細長い三角形を減らす）。
5. 3D 文字は、平らな字を `depth` で押し出す（側面は輪郭の辺から作る）。

- 試作 S0-09 で、限定的溶解だけで穴が保たれることを確認しました（代表 100 字 × 2 書体 × 20 通りで、壊れた字は 0）。そのため、輪郭のループを取り出して面を張り直す手順は使いません。
- 既定値（試作 S0-09 で決定）

| 用途 | 曲線の解像度 | 角度 | 1 字の平均三角形数（ゴシック / 明朝） |
|---|---|---|---|
| 通常 | 6 | 1° | 100 / 303 |
| モバイル最適化 | 4 | 1° | 74 / 210 |

- 角度を 5° 以上にすると、明朝体で形の誤差が大きくなる（面積で最大 8%）ため、角度の上限は 3° にします。
- **1 字の上限に収める**（`fit_text_mesh`）：モバイル最適化では、1 字の三角形を仕様書 §10.3 の上限（2D 300・3D 1000）に収めます。解像度 4 → 3 → 2 の順に作り直し、それでも超える字（明朝の画数の多い字。例：「鬱」は解像度 4 で 2D 807）は減面（Decimate の Collapse）で上限にします。2D の字は、減面の後に穴の数が変わっていないかを数え直して報告します（`holes_kept`。代表 100 字では変わらなかった）。

### 11.3 行メッシュへの切り替え

- 対象：モバイル最適化が ON で、保持の動きが「静止」、2 文字以上、表示が 1 秒以上続く行（TMP 変換が ON なら 3D の行だけ）。仕様の「行単位の動き（行全体の脈動など）」は、文字のトラックが行で共通にならないため、段階 5 では対象にしません。
- ベイク時（`core/bake.py`、視線の誘導の後）に、行の全文字を静止姿勢で並べた `line_mesh` ノード（`<行>_line`、メッシュ `line:<行>`）を作ります。全文字の登場が終わった時刻に、文字ノードを非表示・`line_mesh` を表示に切り替え、最初の文字の退場の開始時刻に逆に切り替えます。
- 文字ごとに色が違うので、行メッシュは頂点の色を持ちます（`meshes.bin` の頂点の色。§9.3 の flags の 4）。マテリアルは `text_line`（`LyricLive/TextVC`）。
- モバイル最適化では、文字のマテリアルを 1 つにまとめ（`text`）、色は全文字の `color` のトラックで与えます。

### 11.4 目安の検査

「目安の検査」ボタン（プレビュー・出力のパネル）で、Unity 出力と同じ設定のベイクから次の値を数え、仕様書 §10.3 の上限と比べます（`export_unity/budget.py`。0.5 秒ごとに数える）。

| 項目 | 数え方 |
|---|---|
| 1 字の三角形（2D・3D） | 出力と同じ手順で作った字のメッシュの最大 |
| 表示中の三角形 | 各時刻で表示中のノード（親も表示中）のメッシュの三角形の合計の最大 |
| 同時のパーティクル | 連続の発生源は最大数、一斉の発生源は発生から寿命（子の寿命を含む）までの数の合計の最大。モバイル最適化ではパーティクルの割合を掛ける |
| マテリアルの数 | manifest のマテリアルと、パーティクルの描画の組み合わせ（加算・半透明 × 2D・3D）の数 |

- 上限は出力のパネルで変えられます（既定は §10.3 の値）。TMP の文字は数えません（改善メモ）。

---

## 12. Blender のプレビュー（`preview/`）

- コレクション：`LyricLive`（`LLB_Text`・`LLB_Background`・`LLB_Particles`・`LLB_Guide`・`LLB_Gimmicks`・`LLB_Camera`）。作り直しは、このコレクション以下のオブジェクト・パーティクルのメッシュ・アクション（ドームのマテリアルのノードツリーのアクションを含む）を削除してから行います。字形と内蔵メッシュ（`llb_builtin` の印）は共有して残します。
- マテリアル：`LLB_Text`（文字）、`LLB_Far`（遠景）、`LLB_Glow`（誘導の光）、`LLB_Dome`（ドーム。版の番号 `llb_version` が違えば作り直す）、`LLB_ParticleAdd`・`LLB_ParticleAlpha`（2D パーティクル。アトラスの画像 `LLB_ParticleAtlas` を .blend に格納）、`LLB_Particle3D`。
- 「生成」「おまかせで作る」は、`ui/planning.build_preview` で、プロパティ → Settings → Plan → BakedScene → シーンの順に作ります。
- アニメーションの書き込み（`animation.py`）：Blender 5.x のレイヤードアクションの API を使います。
  - オブジェクトごとにアクションを作り、`fcurve_ensure_for_datablock` または `layers → strips → channelbag(slot)` の `fcurves.new()` で F カーブを作ります。
  - `keyframe_points.add(n)` と `foreach_set('co', ...)` でまとめて書き込み、補間を一括で設定します。
  - 実際の書き込み手順（試作 S0-02 で確定）：`action.slots.new(id_type='OBJECT')` → `action.layers.new()` → `layer.strips.new(type='KEYFRAME')` → `strip.channelbag(slot, ensure=True)` → `fcurves.new(data_path, index)` → `keyframe_points.add(n)` → `foreach_set('co', …)` と `foreach_set('interpolation', …)`（整数 1 ＝ LINEAR、0 ＝ CONSTANT）→ `fcurve.update()`。最後に `animation_data.action` と `animation_data.action_slot` を設定する。
  - 速さ：6 万キーで 0.04 秒、300 万キーで 2.8 秒（試作 S0-02）。
- マテリアル：文字は「Object Info の Color/Alpha × 発光」の共有マテリアル `LLB_Text`（オブジェクトごとのマテリアルを作らない）。透明は、マテリアルのレンダリング方法を Blended にします。視線に対して斜めの面ほど暗くし（Layer Weight の Facing）、3D 文字の側面を見分けられるようにします（発光色だけでは、側面と表面が同じ色になり、文字がにじんで見えた）。
- 観客カメラ：原点・目線の高さ・正面 +Y・視野角 90°（`LLB_AudienceCamera`。作り直しでも残す）。「観客カメラ」ボタンは、カメラからの視点とマテリアルプレビューに切り替えます。
- 文字のオブジェクトはノード ID（`llb_node`）を持ちます。統合テストは、Blender で再生した位置が `core` の計算と一致すること（3 mm 以内）を確かめます。
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
| 5. おまかせ | おまかせで作る、前の案/次の案（n / m）、雰囲気・スタイル、ここだけ変える（スタイル／アクセントの色／雰囲気／文字の構成／パーティクル／背景） |
| 6. セクションと行 | セクションの UIList と詳細（種別・テーマ・背景・トランジション・鍵）、行の UIList と詳細（仕様書 §6.2。鍵・選び直す・視線の誘導・この行のパーティクル・この行からの背景・トランジション） |
| 7. 演出 | 強さのスライダー（動き・パーティクル・装飾・密度・背景の切り替え・視線の誘導）、コマ打ち、フラッシュ、独自のアクセント、パノラマ画像、部品の ON/OFF（種類を選んで UIList。まとめて入/切） |
| 8. プレビュー | 生成、削除、観客カメラ、シード、ビュー変換が「標準」でないときの警告と切り替え。目安の検査は段階 5 |
| 9. Unity 出力 | プロジェクト、エディタ、オプション、出力、状態とログ |
| 最適化 | mesh_optimizer のパネル（独立） |

- タップ同期（`tap_sync.py`）：モーダルオペレーターです。開始時に `screen.animation_play` で再生し、`T` キーのイベントの時刻を記録します（時刻の求め方は下の「遅延の測定」と同じ）。記録中は仮のマーカー、終了時に行ごとのマーカー `LLB:<行番号>` を置きます。`Esc` で終了、`Backspace` で取り消し。
- タップの速さ（1×・0.75×・0.5×）：シーンの再生には速さの設定が無いので、1× 未満では `screen.animation_play` を使いません。`_SlowClock` が `aud.Sound.timeStretchPitchScale`（音程を保つ Rubberband。品質 HIGH）で伸ばした曲を音声デバイスで直接再生し、0.05 秒のタイマーで `scene.frame_set` して再生位置に合わせます。シーンの fps・同期・ストリップは変えないので、元に戻す設定もありません。`Handle.position` は伸ばした音声の実時間で進むので、曲の時刻は「(タップの時刻 − 時計の基準) × 速さ」です。遅延の補正は実時間の値なので、曲の時間では「遅延 × 速さ」を引きます。再生中の Space は無視します（シーンの再生が始まると曲が二重に鳴る）。曲が無ければ、警告を出して通常の速さで行います。
  - タップの途中で速さを変えられます。タイマーで `tap_speed` の変化を見つけると、それまでのタップを曲の時刻に確定し（`_settle`）、`Sound.limit` で今の位置から新しい速さで再生し直します（待ち時間は約 35〜60 ms）。途中で 1× に戻したときも `_SlowClock` のままです（通常の再生には戻さない）。1× でも伸長の処理を 1.0 倍で通します（`limit` だけの音声は `Handle.position` が異常な値のまま進まないため。1.0 倍でクリックの位置は変わらない）。曲の時刻は「offset ＋ 位置 × 速さ」です。`limit` の読み始めの誤差は WAV・FLAC・MP3 で 0、OGG で約 23 ms、M4A は未確認です。
  - 同時に動くのはタップ同期と遅延の測定のどちらか 1 つです（`_current`）。動作中は開始のボタンの `poll` が偽になり、「タップ同期」のボタンは「終了」（`llb.tap_stop`）に変わります。「終了」は印を立てるだけで、次のタイマーイベントでモーダルが終わります。
  - 通常の再生の時計（フレーム）と `aud` の時計の差は測っていません（通常の再生中は `aud` のハンドルの位置が進まないため、同時に比べられない）。差は理論上おおむね半フレーム以内で、0.5× の曲の時間では 60 fps で約 4 ms、24 fps で約 10 ms です。
  - `Sound.pitch` の方式は音程が下がる（0.5× で 1 オクターブ）ので使いません。
- 案内の表示（`ui/overlay.py`）：タップ同期中は次の行の歌詞と行番号を、遅延の測定中は「予備拍 n/4：聞くだけ」「クリックに合わせて T（n/16）」を、3D ビューの上部中央に大きく表示します。ステータスバーの文字は小さく、Blender 5 の「アニメプレイ」の表示に紛れて見落とされたため（段階 1 の確認で判明）。
- マーカーから取り込む：`LLB:<行番号>` のマーカーのうち、タップの時刻のフレームから動いたものだけを取り込みます（動かしていないマーカーは、フレームより細かいタップの時刻を保つ）。
- 再生の終わり：再生は最後のフレームから先頭に戻って繰り返し、モーダルはイベントが来たときしか動きません。そのため、0.05 秒のタイマーイベントで定期的に判定し、フレームが先頭に戻ったことも終わりとみなします（2 周目のフレームが時刻の換算に混ざるのを防ぐ）。
- 遅延の測定：拍のクリック音のサウンドストリップを一時的に作って再生し（他のストリップは消音。終了後にシーンの範囲・消音・同期の設定を元に戻す）、利用者に拍に合わせて 16 回タップしてもらいます（4 拍の予備拍の後）。測った値は、ファイル（`tap_latency_ms`）とプリファレンスの両方に保存し、測っていないファイルではプリファレンスの値を使います。手で入力した値も、そのファイルの値として使います。
  - フレームが切り替わった瞬間を基準にするため、最大 1 フレームの一定の偏りがあります。測定とタップ同期が同じ fps なら打ち消されるので、測定時の fps（`latency_fps`）を記録し、違う fps でタップ同期を始めたら警告を出します。理論上の拍の時刻との差の中央値を `tap_latency_ms` にします。
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
| `core/`・`text/fontinfo.py` | `tests/run_core.sh`（Blender 同梱の Python で `python -m unittest discover -s tests/core -t .` を実行。Blender 自体は不要。numpy が必要なため、WSL 等の Python に numpy が無くても動くように同梱の Python を使う） |
| フォント解析 | フォントファイルはリポジトリに置かず、テストの中で最小構成の TTF・OTF・TTC を組み立てて検証する |
| モーダル操作 | `tests/blender/test_tap_modal.py`：`--enable-event-simulate` 付きの GUI の Blender で、キー入力を送ってタップ同期と遅延の測定を確かめる（約 30 秒、ウィンドウが開く） |
| `text/fontinfo.py` | テスト用の OFL フォント（リポジトリに置けるライセンスのもの）で、送り幅・cmap を検証 |
| 部品の契約 | 全部品について、登場の p=1・退場の p=0 で恒等になること、例外を出さないこと |
| 段階 3 の core | `tests/core/test_world.py`：配色のコントラスト、全パーティクルの状態（有限・目から 0.6 m 以上・期間外は無い・破裂の粒が枠に収まる）、アトラスとメッシュ、テーマ・背景・トランジション（切り替えの間はドームが今の背景を見せる）、「ここだけ変える」の独立性、行の選び直し、フラッシュの間隔、コマ打ち、動きの強さ、視線の誘導、おまかせ、スペクトラム、速さ |
| 段階 3 の統合 | `tests/blender/test_phase3.py`：おまかせ・履歴・鍵・ここだけ変える・行の背景の上書き・強さのスライダー、パーティクルのプレビュー＝core（全粒の中心）、ドームの色（EEVEE で 33×19 を描き、地平線の画素が背景の色と一致）、4 分の曲の速さ、訳の漏れと衝突。共通の処理は `tests/blender/common.py` |
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

### 17.3 段階 2 の実装による変更

| 箇所 | 変更 | 理由 |
|---|---|---|
| §7.1 | 視角の既定を、本文 3.5°・強調 5.5° にした | 2.5° では、視野角 90° の観客カメラで字幕のように小さかった |
| §5.5 | 残る行の位置（6 か所）と、レイアウトの属性 `big`・`anchored`・`keepable` で重なりを避ける | 単体テストの総当たり（30 シード × 2D/3D）で、別の行の文字の重なりが 0 になることを確認 |
| §5.6 | レイアウトに `group_motion`・`shown` を追加 | 迫ってくる・回る立方体は行全体が動く。立方体の横の面の文字は、真横から見ると正面の文字に重なった |
| §12 | 文字のマテリアルで、斜めの面を暗くする | 3D 文字の側面が見分けられなかった |
| 部品 | 「分解→集合」「爆散」は文字単位。「粒子から集まる」「粒になって散る」は近似 | 字形の部品への分解・Unity のパーティクルは後の段階（改善メモ） |
| 多言語 | Blender 本体に訳のある英語の文言は使わない（例：`Front` → `Facing Front`） | アドオンの訳より本体の訳が優先され、「見出し」が「表示」、「等幅」が「モノラル」と出ていた（段階 1 からの不具合）。統合テストで衝突と訳の漏れを検出する |

### 17.2 段階 1 の実装による変更

| 箇所 | 変更 | 理由 |
|---|---|---|
| §4.1 | フォントの役割を、4 つの `PointerProperty` にした。行に `source`・`tap_time`・手動の時刻を追加した | 4 つ固定の役割は、コレクションより扱いが単純。時刻の出どころを区別しないと、優先順位を守れない |
| §5.3 | タップの遅延は、記録するときに差し引く | マーカーの位置と行の開始時刻を一致させるため |
| §5.3 | セクション推定の区切りを相対的な基準にし、サビの継続・同じ種別の結合・先頭の統合方向を決めた | 固定の 2 拍では、ほぼ全行が区切りになった（単体テストで確認） |
| §5.4 | 高域フィルターを周波数領域で計算し、テンポの範囲の端も補間する | numpy で一括処理するため。端のテンポの誤差を ±1 BPM 以内にするため |
| §5.4 | スペクトラムは段階 3 で実装する | 使うのは段階 3 以降（パーティクル・ギミック）のため |
| §5.3 | 歌詞を読み直したときの行の対応を、行番号から文字列の照合に変えた | 行を挿入すると、以降の行のタップの時刻がずれたため（改善メモ） |
| §13 | 遅延を測ったときと違う fps でタップしたら警告する | フレームの時計の偏りは、同じ fps でしか打ち消されないため（改善メモ） |
| 全体 | Python 3.11・numpy 1.26（Blender 5.0）でも動くように書く | Blender 5.0 の同梱の Python は 3.11、numpy は 1.26。numpy 1.x では uint64 の配列と Python の整数のビット演算ができない（5.0 での確認で発見） |
| §13 | モーダルにタイマーを付け、再生が先頭に戻ったら終える | 最後のタップの後に入力が無いと、終わりを見逃して 2 周目に入った（自動テストで発見） |

### 17.4 段階 3 の前に行った変更（段階 2 の確認での要望）

| 箇所 | 変更 | 理由 |
|---|---|---|
| §5.7・仕様書 §7.4 | 残る行は、正面に出てから、次の行の直前に脇の位置へ移る。セクションの最後の行は正面のまま残る | 観客カメラ（VR の視野）の外に、いきなり文字が出て気づきにくかった（確認者の要望） |
| §8.4・仕様書 §7.6 | 視線の誘導（光の筋・予兆の灯り・ドームに差す光）を加えた。Udon 版は段階 5 | 同上。矢印のようなあからさまな表現を避け、全体の演出と混ざらないようにする |
| §5.7 | 床のレイアウトを残る行に使わない。残る行の退場を、その場で消える種類に限る | 全行を残す設定の総当たりで、床の行同士や、崩落で落ちる行が重なっていた（段階 2 の不具合） |
| §5.7 | キーの時刻を 0.1 ms 単位にそろえる | float32 のフレーム番号で 2 つのキーが重なり、Blender で位置が最大 3 mm ずれた（段階 2 の不具合） |

### 17.5 段階 3 の実装による変更

| 箇所 | 変更 | 理由 |
|---|---|---|
| §8.1・§12 | パーティクルのプレビューを、Geometry Nodes の Simulation Zone から、core の閉じた式をフレームごとに計算してメッシュに書く方式に変えた（`preview/particles.py`） | シミュレーションは再生位置を飛ばすと結果が変わり、core の計算と一致することを検査できない。閉じた式なら、どのフレームでも同じで、テストで全粒の位置を照合できる |
| §8.2・§12 | ドームのパラメータを、マテリアルの Value / RGB ノードの値のアニメーションにした（カスタムプロパティ＋Attribute ノードをやめた） | Blender 5.0 の EEVEE では、1 つのマテリアルが読めるオブジェクトの属性の数を超えて、ドームが黒くなった（5.2 では表示された）。ノードの値のアニメーションは版によらず動き、Unity のマテリアルのプロパティのアニメーションにもそのまま対応する |
| §8.2 | 切り替えで A へ B をコピーするのをやめ、`next`（見せる組）と、両向きに動く `progress` にした | コピーの瞬間に、同じフレームで 2 つの値を飛ばす必要がなくなる（キーの補間で一瞬崩れることがない） |
| §8.2 | ドームの UV を使わず、方向から色を求める | 正距円筒の UV は、アイコスフィアの継ぎ目で歪む |
| §8.1 | テクスチャの描画を `core/atlas.py` に置いた（PNG の書き出しも標準ライブラリで行う） | プレビュー（`preview/`）は `export_unity/` を import しない（§3 の依存のルール） |
| §8.4 | 誘導の光の色を、文字色が暗いときは白へ寄せる。粒の間隔を 0.03 秒に詰めた | 昼の空の上の暗い文字色では、加算の光が見えなかった。0.05 秒の間隔では、点線の矢印のように見えた |
| §5.5 | 行の選び直し（`seed_offset`）は、残す・残さないの判定と、直近の重複を避ける履歴に、選び直す前の結果を使う | 選び直した行の結果が履歴に入ると、後ろの行の重みが変わり、ほかの行まで変わってしまう |
| §4.1 | Plan を保存しない。部品の ON/OFF は `parts`（種類・キー・入/切）の Collection | 決定的なので保存は不要（段階 4 で必要なら保存）。UIList で絞り込んで表示するため |
| §5.4 | スペクトラムは曲全体を基準にした dB（上位 60 dB）を 0..1 にする | 帯域ごとに正規化すると、帯域どうしを比べられず、スペクトラムバーの高さの意味がなくなる |
| §13 | 長い項目名（レイアウト・パーティクル・背景・トランジション・パノラマ画像）は、名前を欄の上に置く | 狭いサイドバーで「レイア…」のように切れた |
| 段階 2 | 「おまかせ」のレイアウトでも「3D 文字の行用」の警告が出ていたのを直した | 「おまかせ」の項目にも説明文があり、その有無で判定していた |
| §8.2・§12 | 遠景のマテリアルを Dithered（深度を書く）にした | 段階 3 の確認で、観客カメラで山並みが文字を隠していた（半透明どうしは原点の距離で描く順が決まり、帯の原点は観客の足元にある） |
| §5.5 | 文字の配色の基準を、シルエットがあればその色にした | 夕焼け・夜明けでは、明るい空に合わせた暗い文字が、暗い街並み・山並みに溶け込んでいた |

### 17.6 段階 4 の実装による変更

| 箇所 | 変更 | 理由 |
|---|---|---|
| §9.1 | 組み立ての印を `_llb_build.pending` にした | テスト用プロジェクトの段階 0 の試作が `_pending.llb` を監視しており、本実装の出力を誤って組み立てようとする |
| §9.1 | 出力の前に Timeline パッケージの有無を確かめる | 空のプロジェクトには Timeline が無く、組み立てのスクリプトがコンパイルできない |
| §9.2 | manifest の曲線に、Unity の型・属性・成分の名前を持たせた。パーティクルは Unity 向けの説明を Python 側で作る | ロジックを Python に集める（§1 の方針 2）。C# は値を写すだけになる |
| §10.2 | 組み立てをプレビュー用のシーンで行う | 開いているシーンを変更済みにしない（MCP で `isDirty = false` を確認） |
| §10.3 | どちらのモードも同梱シェーダーを使う | 試作 S0-07 で Quest・iOS での表示を確認済み。アニメーションするプロパティ名をシェーダーごとに置き換える必要もなくなる |
| §10.6 | クリップの後の外挿の代わりに、ディレクターの Hold を使う。マーカーのトラックは作らない | `TimelineClip.postExtrapolationMode` は読み取り専用 |
| パーティクル | テクスチャのタイルを選ぶ `startFrame` は、タイル番号ではなく `(番号 + 0.5) / 16` | Unity では 0〜1 の割合（番号を入れると 0.9999 に丸められ、空のタイルになった） |

### 17.7 段階 5 の実装による変更

| 箇所 | 変更 | 理由 |
|---|---|---|
| §3 | `mesh_optimizer/` を本体のパッケージの中に置き、単体の zip は `--source-dir` で作る | Extension の zip には、パッケージの外のモジュールを入れられない |
| §11.2 | 1 字の上限を超える字は、解像度を下げ、それでも超えたら減面する（`fit_text_mesh`） | 明朝の画数の多い字は、解像度 4 でも上限を大きく超えた（「鬱」は 2D 807・3D 3284） |
| §11.3 | 行メッシュは頂点の色を持ち、モバイル最適化では文字のマテリアルを 1 つにする | 文字ごとの色を残したまま、マテリアルの数を減らす |
| §11.3 | 行メッシュの対象を「静止」の行だけにした | 行単位の動きは文字ごとのトラックで表しており、行で共通にならない |
| §8.4・§10.7 | 誘導 1 回分の粒と光の玉を、目の位置の親の子にした | Udon が親だけを回せば、Timeline のアニメーションと競合しない |
| §10.7 | 同期のスクリプトを全曲で共有し、組み立ての印を 2 つ（`_llb_build.pending`・`_llb_udon.pending`）にした。型は `MonoScript.GetClass()` で取る | 曲ごとのスクリプトは不要。スクリプトのコンパイルの後でないと部品を付けられない。U# が同名のクラスを別のアセンブリにもコンパイルする |
| §10.8 | フォントアセットを `<曲>/FontAssets/` に作り、組み立て直しで使い回す | `Generated/` は毎回消える。Udon の 2 段階めではフォントファイルが削除済み。`Fonts` は Windows で `fonts` と同じフォルダーになる |
| §10.1 | エディタのスクリプトを asmdef にまとめ、TMP の有無を `versionDefines` で切り替える | TMP の無いプロジェクトでもコンパイルできるようにする |
| §10.7 | 親を回す方式をやめ、Udon が `LateUpdate` で粒の位置を置く | 段階 5 の確認で、視線の方向を変えても誘導が見えなかった。親を回すだけでは、光の筋の長さが「推定の視線と行の角度」のままで、実際の視線に届かず、角度が 0° の行は長さも無かった |
| §8.4 | 粒の直径を 0.026 倍から 0.06 倍にし、移動の時間を角度で 0.7〜1.2 秒にした。「あり」の行は最低 45° の光の筋にした | 同じ確認で、光が小さく、推定の視線が行の上にある行では、点が 1 つ見えるだけだった |
| §10.1 | `LLBSync.cs` の内容をテンプレートと比べて更新する。Play の終了時にも組み立ての印を探す | 既存のプロジェクトの `LLBSync.cs` が更新されなかった。Play 中に届いた印が放置されていた |

### 17.8 段階 6 の実装による変更

| 箇所 | 変更 | 理由 |
|---|---|---|
| §3・§8.3 | 内蔵の基本形を bmesh ではなく numpy で作る（`core/gimmick_shapes.py`） | core に置けて、単体テストで閉じた形・面の向きを確かめられる。プレビューと出力で同じデータになる |
| §8.3 | 「開く」をシェイプキーではなく部品の回転で作った。ディゾルブは新しいプロパティを足さず、`color` の透明度を使う | 独自形式のシェイプキーも新しい曲線の種類も要らず、既存の経路をそのまま使える |
| §8.3 | 利用者の物体の色を、テクスチャごと頂点の色に写す | UV とテクスチャの出力が要らず、全物体を 1 つのマテリアルで描ける |
| §8.3 | 利用者の物体の向きをそろえない（正面は -Y とみなす） | 正面は自動で判定できない |
| §8.3 | 利用者の追加の単語は JSON ではなく `タグ=語,語; ...` の 1 行 | プリファレンスの 1 行で編集できる |
| §8.3 | スペクトラムバーの半径を 4.2 m にした | 文字（3.5 m）の後ろに置く |
| §13（タップ同期） | タップの速さ（1×・0.75×・0.5×）を追加した。JIZURA の新しい版の機能だが、`playbackRate` に当たるものがシーンの再生に無いので、`aud` で直接再生する。JIZURA と違い、音程を保つ | 確認者の要望。曲が速いとタップしづらい |
| §13（タップ同期） | タップの途中で速さを変えられるようにした。動作中は開始できず、ボタンが「終了」に変わる | 確認者の確認で、変更が次の開始まで効かず、「タップ同期」を何度も押せてしまい、動作がおかしくなった |
| §13（タップ同期） | 再生の時計は、フレームが最初に見えた時刻だけを記録する | AUDIO_SYNC では音声のクロックがバッファ単位で進み、同じフレームが繰り返される。繰り返しも記録すると、中央値が 1 フレーム遅れることがあった |
| §10.2 | エディタでは、プレビューシーンを 1 フレーム後に閉じる | UdonSharp の `delayCall` が、閉じた後の部品に触れて例外を出した |
