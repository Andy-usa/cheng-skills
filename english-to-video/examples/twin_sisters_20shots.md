# 示例：双胞胎姐妹 + 体育老师（20 镜冰雪奇缘模板）

人教版 4-5 年级英语课本短文「Mandy and Sandy are twin sisters...」的标准 20 镜分镜模板。可以直接拿来跑，也可以作为相似题材（双胞胎、家庭、校园误会）的镜头序列骨架，把人物 / 动作改写后复用。

配套机读文件：[`twin_sisters.scenes.json`](./twin_sisters.scenes.json) ——直接 `make_video.py --json examples/twin_sisters.scenes.json --phase all` 即可。

---

## 课文原文（126 词）

> Mandy and Sandy are twin sisters. They both have long blonde hair and are of the same height. They usually wear the same dresses. They look the same and study in the same middle school. Although they aren't in the same class, they have the same PE teacher, Mr Brown. It is the first PE class. Mandy and her classmates go to have the PE class. The class begins. But when Mr Brown sees her, he is very surprised and says to her, "You had my class just now. Why do you come to my class again?" Mandy is also very surprised to hear this, but she understands soon. She smiles and says, "Mr Brown, you may have made a mistake. I have a twin sister."

## 角色映射（→ 冰雪奇缘原版）

| 课文角色 | Frozen 映射 | 备注 |
|---|---|---|
| Mandy | **艾莎 Elsa** | 长金发法式辫，浅色公主裙 |
| Sandy | **安娜 Anna**（重染金发匹配 Elsa） | 双马尾，雀斑，与 Elsa 同款裙、同身高 |
| Mr Brown | **克里斯托夫 Kristoff**（换装体育老师） | 棕短发 + 运动夹克 + 哨子 |

---

## 全程统一固定参数

> 冰雪奇缘电影画风，迪士尼 3D 卡通，电影级光影，16:9，高细节，超清渲染，柔和冰雪质感，唯美童话场景，角色高度还原冰雪奇缘原版人物，画面生动童趣，儿童动画质感，电影抽帧镜头感

> ⚠️ 写 `prompt` 字段时**不要**重复这串后缀——`make_video.py` 已经在最后自动拼好。

---

## 20 镜序列

| # | 课文片段 | 镜头 prompt（中文） |
|---|---|---|
| 1 | Mandy and Sandy are twin sisters. | 冰雪奇缘画风，全景镜头，城堡庭院场景，艾莎与安娜并肩站立，两位金发公主，身形身高一致，同款浅色长裙，温柔对视，冬日清新环境，柔和自然光，迪士尼电影质感，16:9，电影抽帧画面 |
| 2 | They both have long blonde hair | 冰雪奇缘画风，中景特写，艾莎长发金发细节刻画，柔顺金色长发，精致五官，冰雪城堡背景，柔和漫反射光线，童话风配色，高清细节，16:9 |
| 3 | and are of the same height. | 冰雪奇缘画风，全身镜头，安娜笔直站立，标准身高比例，优雅体态，城堡露台场景，淡蓝色冰雪色调，唯美氛围感，迪士尼3D建模质感，16:9 |
| 4 | They usually wear the same dresses. | 冰雪奇缘画风，双人中景，艾莎和安娜身穿一模一样的公主连衣裙，款式配色完全相同，并肩行走在城堡走廊，暖柔室内光影，童趣可爱，16:9 |
| 5 | They look the same | 冰雪奇缘画风，双人正面镜头，艾莎安娜五官长相相似，容貌酷似，并肩微笑对视，冰雪森林远景背景，电影级构图，16:9 |
| 6 | and study in the same middle school. | 冰雪奇缘画风，远景镜头，宏伟冰雪城堡学校建筑群，艾莎安娜一同走入校园，童话风校园场景，白雪点缀环境，16:9 |
| 7 | Although they aren't in the same class, | 冰雪奇缘画风，分隔画面，左右对比，艾莎安娜走进不同教室门牌，虽同校不同班级，柔和冷色调，校园走廊场景，细腻画面细节，16:9 |
| 8 | they have the same PE teacher, Mr Brown. | 冰雪奇缘画风，中景人物，冰雪奇缘原版克里斯托夫换装体育老师造型，棕色短发，休闲运动穿搭，温和严肃神态，操场背景，16:9 |
| 9 | It is the first PE class. | 冰雪奇缘画风，操场全景镜头，冬日户外运动场，绿植与白雪结合，体育课堂场景搭建，空旷唯美环境，电影镜头感，16:9 |
| 10 | Mandy and her classmates go to the PE class. | 冰雪奇缘画风，群像中景，艾莎跟随一群小伙伴走在操场，结伴前往体育课，孩童活泼动态，轻松欢乐氛围，16:9 |
| 11 | The class begins. | 冰雪奇缘画风，近景镜头，操场场地画面，体育课正式开始，阳光洒落地面，简洁干净户外场景，柔和光影层次，16:9 |
| 12 | But when Mr Brown sees her, he is very surprised | 冰雪奇缘画风，特写镜头，体育老师克里斯托夫皱眉惊讶表情，目光看向前方的艾莎，神态疑惑，表情生动夸张，16:9 |
| 13 | and says to her, | 冰雪奇缘画风，双人对话镜头，体育老师面对艾莎，抬手疑惑询问，肢体动作自然，操场背景虚化，聚焦人物互动，16:9 |
| 14 | "You had my class just now. Why come again?" | 冰雪奇缘画风，人物近景，体育老师开口说话神态，神情不解，户外自然光打亮人物，迪士尼细腻表情刻画，16:9 |
| 15 | Mandy is also very surprised to hear this, | 冰雪奇缘画风，艾莎正面特写，满脸意外惊讶的神情，双眼睁大，呆萌可爱表情，浅淡冰雪背景，16:9 |
| 16 | but she understands soon. | 冰雪奇缘画风，艾莎半身镜头，瞬间恍然大悟的神态，眼神灵动，情绪转变自然，童话风色彩搭配，16:9 |
| 17 | She smiles and says, | 冰雪奇缘画风，艾莎微笑侧身，温柔礼貌的笑容，气质优雅，冬日操场环境，柔和氛围感，电影抽帧质感，16:9 |
| 18 | "Mr Brown, you may have made a mistake." | 冰雪奇缘画风，互动中景，艾莎对着体育老师从容解释，肢体放松，沟通姿态自然，清新治愈画面，16:9 |
| 19 | "I have a twin sister." | 冰雪奇缘画风，回忆感远景，画面角落虚化浮现安娜身影，暗示双胞胎姐妹设定，朦胧唯美特效，16:9 |
| 20 | Mandy and Sandy are twin sisters! (recap) | 冰雪奇缘画风，双人收尾镜头，体育老师恍然大悟微笑，艾莎从容站立，冬日操场全景收尾，画面完整和谐，童趣治愈，16:9 |

---

## 适配说明

1. 全程绑定冰雪奇缘原版人物建模，艾莎/安娜替代原文双胞胎姐妹，体育老师用克里斯托夫改写适配，人物还原度拉满。
2. 全部 16:9 画幅、电影抽帧质感，完美适配旁白动画剪辑。
3. 语气、画面节奏贴合 4 年级英文旁白，画风低龄友好、生动童趣，适合课本动画使用。
