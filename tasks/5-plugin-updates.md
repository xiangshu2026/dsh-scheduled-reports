生成一份"DSH 插件更新检查报告"。

【执行效率要求（最重要，先读这段）】
- plugin-updates.txt **只读一次**，读完立刻开始写报告。
- **不要自己去查 npm registry、不要自己读 node_modules、不要运行任何 PowerShell 去核对版本**——
  所有数据都已在 plugin-updates.txt 里采集好了，自己查会失败而且非常耗时。
- 报告文件是**成品**，只写结论和表格。

【输出格式的硬要求】
报告正文必须是成品中文 Markdown，直接面向读者。
**严禁**在报告文件里出现：思考过程、犹豫、自我辩论、英文段落、对你所遵循的
规则的讨论。写进文件里的每一句都应该是给读者看的。

【关于已存在的同名报告文件 —— 不用犹豫】
如果目标报告文件已经存在（上一次运行留下的），**直接覆盖它**。这是预期行为，
属于本任务允许范围，不是违规。不要为此分析、权衡或反复判断，覆盖它然后继续。

【数据来源】
当前工作目录下的 plugin-updates.txt，是刚由外部程序用完整权限采集的，准确可信。
报告里所有插件数据都以它为准。

【plugin-updates.txt 各段含义】
- GENERATED_AT      采集时间
- DEP_COUNT         检查的插件总数
- BUNDLE_COUNT      已启用的插件数
- PLUGIN_STATUS     逐插件明细，格式：
                      name | installed | latest | status | declared | published
                    其中 status 的取值：
                      current       已是最新
                      outdated      有新版本
                      ahead         本地版本比 registry 还新（罕见，通常是预发布）
                      registry-error 查不到（本地 link:/file:/github: 来源的插件属正常）
                      installed-missing 声明了但没装
- SUMMARY            CHECKED / OUTDATED_COUNT / CURRENT_COUNT / ERROR_COUNT
- OUTDATED_DETAIL   待更新明细，格式：name | installed | latest | published
- ERROR_DETAIL      查不到的项目名单
- PREVIOUS_STATE    上一次检查时的版本记录（first-run 表示第一次）

【报告需要包含】
1. **开头两三句中文总结**：这次检查发现几个可更新，分别是哪几个，一句话说清
   "要不要现在升级"。
2. **可更新的插件**（表格）：插件名、当前版本、最新版本、发布时间。
   如果 OUTDATED_COUNT=0，明确写"全部已是最新，无需操作"。
3. **已是最新的插件**：只列名字和版本，不用展开。
4. **查不到更新的插件**：单独一节说明这些是本地/私有来源插件（link:、file:、
   github:），npm 上本来就没有，**不是错误，不用管**。
   要列出名字，但语气是"正常，无需处理"。
5. **结尾加一节"采集说明"**：写明数据来自 plugin-updates.txt、采集时间
   GENERATED_AT、检查了多少个插件。

【语气要求】
- 中文，Markdown 格式
- 保存到当前工作目录
- 文件名必须是：插件更新检查-当天日期.md，日期格式为 YYYY-MM-DD
- 面向主人，简洁直接。可更新的要说清"升不升"，不要写一堆免责声明。

【严格限制】
- 只允许新建或覆盖这一个报告文件，不要修改、移动、重命名或删除任何其他文件
  （包括不要改动 plugin-updates.txt）。
- 不要安装、升级、卸载任何插件——**这份报告只做检查，不做任何变更**。
  升级必须由主人自己决定后再执行。
- 不要修改任何配置文件。
- 某项数据缺失就写"未采集到"。
- 不要问任何问题，完成后直接结束。
