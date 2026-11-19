#!/usr/bin/env python3
"""Build the reviewed canonical chemistry concept layer from textbook occurrences."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CANONICAL_DIR = DATA_DIR / "canonical"
GROUPS_PATH = ROOT / "scripts" / "canonical_concept_groups.json"
CONTENT_OVERRIDES_PATH = ROOT / "scripts" / "canonical_content_overrides.json"
CONFUSABLE_PAIRS_PATH = ROOT / "scripts" / "canonical_confusable_pairs.json"
P0_PATH = ROOT / "scripts" / "p0_content_overrides.json"
P1_PATH = ROOT / "scripts" / "p1_content_overrides.json"
P2_PATH = ROOT / "scripts" / "p2_content_overrides.json"
EXTERNAL_PRIOR_PATH = ROOT / "scripts" / "external_prior_labels.json"

ELEMENTS = set(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co "
    "Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb "
    "Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re "
    "Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es "
    "Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()
)
ACRONYMS = {
    "ABS", "ATP", "BOD", "COD", "DDT", "DNA", "GHS", "HDPE", "IR", "LDPE",
    "MS", "NMR", "PET", "PHB", "PMMA", "PTFE", "PVC", "RNA", "SAP", "STS", "TNT",
    "CFCs", "HFCs", "HIV", "PP", "PV", "PE", "PS", "PC", "DMC", "DME", "TDI",
    "VIB", "VIII", "IB", "IIB", "IIIB",
}
INVALID_FORMULA_TOKENS = {
    "OH", "COOH", "CHO", "COO", "CH", "CH2", "CH3", "NH", "NH2", "NH4",
    "SH", "CN", "SCN", "CO3", "HCO3", "SO4", "HSO3", "NO3", "PO4", "HPO4",
    "AlO2", "AlF6", "Fe2", "Fe3", "Cu2", "Mg2", "Al2", "Zn2", "Pb2", "Hg2",
    "Be2", "Cr3", "Cr6", "Fe0", "S2", "ClO", "H3O", "C1", "C1H2", "C2",
    "C3", "C4", "C5", "C6", "C6H5", "C2H5", "CH3CO", "CH3CH", "CH2OH",
    "CHOH", "COH", "CF2", "CHCl", "H12O6", "K3", "KFe", "Pb(Ac)", "SiO4",
}
SUBSCRIPT_TRANSLATION = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
TRADITIONAL_TEXT_TRANSLATION = str.maketrans(
    {
        "劑": "剂",
        "製": "制",
        "麼": "么",
        "為": "为",
        "與": "与",
        "體": "体",
        "學": "学",
        "實": "实",
        "驗": "验",
        "轉": "转",
    }
)
FORMULA_RE = re.compile(
    r"(?<![A-Za-z])((?:\([A-Z][a-z]?\d*\)|[A-Z][a-z]?\d*)+)(?![A-Za-z])"
)
SPECIAL_FORMULA_RE = re.compile(
    r"Δ[HSG]|(?<![A-Za-z])K(?:sp|a|b|w|c)(?![A-Za-z])|"
    r"(?<![A-Za-z])p(?:H|OH)(?![A-Za-z])|(?<![A-Za-z])m/z(?![A-Za-z])|"
    r"离子积|浓度商|平衡常数|溶度积|电离常数|水解常数"
)
EQUATION_RE = re.compile(r"(?:→|⇌|⟶|->|<=>|=)")
TEACHER_META_RE = re.compile(
    r"教学中|教师(?:需|应|可|要)?|讲解时|讲解|需强调|强调|引导学生|要求学生|"
    r"课堂上|本知识点|教学重点|教学应|应强调|应引导|"
    r"让学生|使学生|学生应|学生需|考查|考点|易错|易混"
)
STUDENT_SCOPE_META_RE = re.compile(
    r"本节|本章|本知识点|教材|栏目|习题|实验活动|引言|帮助(?:学生|理解)|"
    r"便于学生|引导学生|讲解|教学|学习时|用于教学|重点|复习|考试|考点|"
    r"知识梳理|课堂|教师"
)
SCOPE_INFERENCE_TEMPLATES = {
    "core_concept": "围绕{name}的基本含义、结构基础和典型表现",
    "property": "围绕{name}的典型表现、影响因素和适用边界",
    "process": "围绕{name}的发生条件、过程和结果",
    "method": "围绕{name}的原理、操作条件、适用范围和限制",
    "representation": "围绕{name}的表示对象、书写规则和使用边界",
    "application": "围绕{name}的应用场景、作用限制和影响",
    "history": "围绕{name}的发展脉络、科学背景和认识变化",
    "safety": "围绕{name}的风险、防护要求、应急处置和使用限制",
    "cross_disciplinary": "围绕{name}与相关学科的联系、结构功能关系和应用边界",
}
SCOPE_ISSUE_CODES = {
    "scope_missing",
    "scope_generic",
    "scope_inferred_from_subtopics",
}
CONDITION_RE = re.compile(r"适用于|条件|前提|在.{0,20}下|需要|必须")
EXCEPTION_RE = re.compile(r"除外|例外|不一定|并非|不包括|不是所有|不能把|需注意")
EXAMPLE_RE = re.compile(r"例如|如|比如|实例")
NEGATIVE_RE = re.compile(r"不是|并非|不能|不属于|不能把")
BOUNDARY_RE = re.compile(
    r"不能|并非|不一定|除外|例外|仅适用|只适用|不适用|通常不|一般不在|需注意|注意"
)
LEADING_LABEL_RE = re.compile(
    r"^(?:[（(]?\d+[）).、]\s*|[一二三四五六七八九十]+[、.．]\s*|"
    r"(?:定义|条件|例外|注意|说明|结论|适用范围|适用条件|边界)\s*[：:]\s*)"
)
PUNCTUATION_RE = re.compile(r"[；;。]+$")

RELATION_LABEL_ALIASES = {
    "氧化还原反应": "氧化还原反应的定义与特征",
    "氧化还原反应定义": "氧化还原反应的定义与特征",
    "氧化还原反应基本概念": "氧化还原反应的定义与特征",
    "氧化还原反应基础": "氧化还原反应的定义与特征",
    "共价化合物": "共价化合物的概念",
    "离子化合物": "离子化合物的概念",
    "元素周期表": "元素周期律与周期表的基本概念",
    "元素周期表结构": "元素周期律与周期表的基本概念",
    "元素周期表的结构": "元素周期律与周期表的基本概念",
    "元素周期表位置": "元素周期律与周期表的基本概念",
    "原电池原理": "原电池的工作原理",
    "原电池基本原理": "原电池的工作原理",
    "原电池基本概念": "原电池的工作原理",
    "电解池工作原理": "电解池的工作原理与离子迁移",
    "化学键理论": "化学键",
    "化学键概念": "化学键",
    "化学键基础": "化学键",
    "化学键类型": "化学键",
    "化学键断裂与形成": "化学键与化学反应的本质",
    "共价键极性": "极性键与非极性共价键",
    "共价键定义": "共价键",
    "离子键定义": "离子键",
    "原电池腐蚀": "电化学腐蚀",
    "电化学腐蚀": "电化学腐蚀",
    "分子间作用力": "分子间作用力与氢键",
    "范德华力": "分子间作用力与氢键",
    "铁的氧化物": "铁的三种氧化物性质",
    "铁的氢氧化物": "氢氧化亚铁与氢氧化铁的制备及转化",
    "沉淀溶解平衡": "难溶电解质的定义与沉淀溶解平衡",
    "活化能": "活化能与反应热",
    "离子晶体": "离子晶体的定义与结构",
    "共价晶体": "共价晶体的定义与结构特征",
    "分子晶体": "分子晶体的定义与构成微粒",
    "晶体与非晶体": "晶体与非晶体的本质差异",
    "质谱法": "质谱法测定相对分子质量",
    "蒸馏": "蒸馏法分离提纯液态有机物",
    "萃取": "萃取与分液操作",
    "加聚反应": "加成聚合反应（加聚反应）",
    "加聚反应原理": "加成聚合反应（加聚反应）",
    "缩聚反应": "缩合聚合反应（缩聚反应）",
    "缩聚反应原理": "缩合聚合反应（缩聚反应）",
    "加聚反应与缩聚反应的区别": "加聚反应与缩聚反应",
    "银镜反应": "乙醛的银镜反应",
    "醛基检验": "醛类的通性及代表物性质",
    "醛基的性质": "醛类的通性及代表物性质",
    "醛基性质": "醛类的通性及代表物性质",
    "胶体": "胶体的分类与丁达尔效应",
    "离子反应": "离子反应的概念",
    "同分异构体": "同分异构现象与同分异构体",
    "官能团识别": "官能团的概念与识别",
    "官能团概念": "官能团的概念与识别",
    "原子半径变化规律": "同周期元素原子半径的周期性变化",
    "杂化轨道理论": "杂化轨道理论简介",
    "杂化轨道理论初步": "杂化轨道理论简介",
    "同周期元素性质递变规律": "同周期元素性质的周期性变化规律",
    "合金基本概念": "合金的定义与性能优势",
    "物质的量概念": "物质的量及其单位摩尔",
    "物质的量浓度计算": "物质的量浓度",
    "碳原子成键特点": "有机化合物中碳原子的成键特点",
    "碳原子的成键特点": "有机化合物中碳原子的成键特点",
    "碳原子成键规律": "有机化合物中碳原子的成键特点",
    "烯烃的加成聚合": "烯烃的化学性质：加成、氧化与加聚",
    "有机化合物的基本分类": "有机化合物的分类方法",
    "高分子基本概念": "高分子化合物的基本概念",
    "高分子概念": "高分子化合物的基本概念",
    "电极反应式书写": "电解池电极反应式的书写",
    "电解池原理": "电解池的工作原理与离子迁移",
    "乙醇分子结构": "乙醇的分子结构与烃的衍生物",
    "弱电解质电离": "弱电解质的电离平衡及其移动",
    "水的电离平衡": "水的电离及离子积常数",
    "化学平衡常数的定义": "化学平衡常数的定义与表达式",
    "原电池与电解池的区别": "电解池与原电池的系统对比",
    "化学反应速率": "化学反应速率的定义与计算",
    "可逆反应概念": "可逆反应与化学平衡状态",
    "化学平衡常数": "化学平衡常数的定义与表达式",
    "同分异构现象": "同分异构现象与同分异构体",
    "分子空间结构": "分子空间结构的基本类型",
    "化学反应的限度": "化学反应的限度与转化率",
    "成肽反应": "成肽反应与肽键",
    "肽键的形成": "成肽反应与肽键",
    "高分子链结构": "高分子链结构与宏观性质的关系",
    "醇羟基性质": "醇的化学性质：取代、消去与氧化反应",
    "弱电解质的电离": "弱电解质的电离平衡及其移动",
    "核苷酸的结构": "核酸的基本组成单位与结构",
    "DNA的双螺旋结构": "DNA的双螺旋结构特征",
    "单体与聚合物的关系": "单体与聚合物链节的相互推断",
    "共价键类型": "共价键的类型（σ键与π键）",
    "铝的化学性质": "铝及氧化铝的两性性质",
    "烷烃的结构": "烷烃的结构特征",
    "溶液的酸碱性": "溶液酸碱性与pH的关系",
    "放热/吸热反应定义": "放热反应与吸热反应",
    "摩尔质量计算": "摩尔质量",
    "热塑性塑料": "热塑性塑料与热固性塑料",
    "氧化钠的性质": "氧化钠与过氧化钠的性质对比",
    "钠的化学性质": "钠的化学性质：与氧气反应",
    "石油裂化": "石油的裂化",
    "有机合成路线设计": "有机合成路线的设计",
    "有机高分子材料": "常见有机高分子材料",
    "传统硅酸盐材料": "传统硅酸盐材料（陶瓷、玻璃、水泥）",
    "酯化反应机理": "酯化反应机理与同位素示踪",
    "电解原理": "电解原理：离子定向移动",
    "合成纤维": "合成纤维的分类与特性",
    "葡萄糖的还原性": "葡萄糖的还原性与化学性质",
    "热化学方程式": "热化学方程式的书写",
    "苯酚的化学性质": "酚的化学性质：弱酸性",
    "VSEPR模型": "价层电子对互斥模型（VSEPR）",
    "多糖的结构": "淀粉与纤维素的结构及水解",
    "原电池构成条件": "原电池原理与构成",
    "原电池正极反应": "原电池的工作原理",
    "焓判据": "焓判据及其局限性",
    "熵判据": "熵判据及其局限性",
    "物质的量": "物质的量及其单位摩尔",
    "氨基酸结构": "α-氨基酸的结构与手性",
    "肽键的结构": "蛋白质的空间结构与肽键",
    "键长": "键长及其影响因素",
    "淀粉的水解": "淀粉的化学性质与水解",
    "氯气与水的反应": "氯气与水的反应及次氯酸性质",
    "糖类的分类": "糖类的定义与分类",
    "离子方程式书写": "离子方程式的书写",
    "牺牲阳极保护法": "牺牲阳极的阴极保护法",
    "原子半径": "同周期元素原子半径的周期性变化",
    "键能": "键能及其计算应用",
    "DNA复制": "DNA分子的复制机制",
    "醛基的还原性": "醛类的通性及代表物性质",
    "高分子结构简式的书写": "高分子结构简式的书写规范",
    "蛋白质结构": "蛋白质的空间结构与肽键",
    "蛋白质的空间结构": "蛋白质的空间结构与肽键",
    "蛋白质变性": "蛋白质的变性",
    "糖类概念": "糖类的定义与分类",
    "糖类分类": "糖类的定义与分类",
    "糖类水解": "糖类的水解反应规律",
    "葡萄糖性质": "葡萄糖的分子结构与性质",
    "葡萄糖的结构与性质": "葡萄糖的分子结构与性质",
    "油脂": "油脂的结构与性质",
    "手性概念": "手性分子与对映异构体",
    "二糖水解": "糖类的水解反应规律",
    "氨基酸的结构": "α-氨基酸的结构与手性",
    "有效碰撞": "有效碰撞与活化分子",
    "活化分子": "有效碰撞与活化分子",
    "酸碱指示剂": "酸碱指示剂变色原理",
    "吉布斯自由能": "吉布斯自由能判据",
    "加成反应": "乙烯的加成反应",
    "电离平衡常数": "电离平衡常数的定义与意义",
    "吸氧腐蚀": "钢铁的吸氧腐蚀",
    "取代反应定义": "取代反应",
    "脂肪族聚酰胺": "脂肪族聚酰胺（锦纶）的合成与性质",
    "吸热反应": "放热反应与吸热反应",
    "放热反应": "放热反应与吸热反应",
    "金属晶体的物理性质": "金属晶体的物理性质解释",
    "构造原理与元素周期表": "构造原理",
    "热固性塑料": "热塑性塑料与热固性塑料",
    "弱电解质的电离平衡": "弱电解质的电离平衡及其移动",
    "氧化剂与还原剂": "氧化剂与还原剂的判断",
    "基态与激发态": "基态与激发态及原子光谱",
    "反应历程": "基元反应与反应历程",
    "孤电子对": "孤电子对对键角的影响",
    "天然橡胶": "天然橡胶与杜仲胶的结构及性质差异",
    "纤维素的化学性质": "纤维素的化学性质与实验",
    "白色污染": "白色污染及其成因",
    "实验式": "元素定量分析与实验式确定",
    "实验式确定": "元素定量分析与实验式确定",
    "共价键理论": "共价键",
    "酮的定义": "酮的定义及丙酮性质",
    "淀粉的化学性质": "淀粉的化学性质与水解",
    "与新制氢氧化铜的反应": "乙醛与新制氢氧化铜的反应",
    "核苷酸": "核苷酸的组成成分",
    "蛋白质的组成": "蛋白质的组成与水解",
    "单糖": "糖类的定义与分类",
    "多糖": "糖类的定义与分类",
    "大气污染物": "大气污染物的来源与次生污染",
    "核糖": "核糖与脱氧核糖的结构",
    "脱氧核糖": "核糖与脱氧核糖的结构",
    "基态原子电子排布": "基态原子电子排布式",
    "引入官能团": "引入官能团的方法",
    "构建碳骨架": "构建碳骨架的方法",
    "摩尔体积": "气体摩尔体积",
    "催化加氢": "乙醛的催化加氢（还原反应）",
    "电子守恒": "电解计算与电子守恒",
    "酸碱中和滴定": "酸碱中和滴定原理",
    "麦芽糖的水解": "蔗糖与麦芽糖的水解特性",
    "芳香烃": "芳香烃与苯的定义",
    "原子经济性": "原子经济性反应与原子利用率",
    "铵盐的性质": "铵盐的性质与检验",
    "电极反应式的书写": "电解池电极反应式的书写",
    "金属键": "金属键与电子气理论",
    "金属晶体": "金属晶体的物理性质解释",
    "分子极性判断": "共价键的极性与分子极性判断",
    "共价键的性质": "共价键",
    "共价键参数": "共价键",
    "共价键方向性": "共价键",
    "合金的定义": "合金的定义与性能优势",
    "晶胞结构": "晶胞",
    "化合价的周期性变化": "同周期元素主要化合价的周期性变化",
    "原子半径的周期性变化": "同周期元素原子半径的周期性变化",
    "对映异构体": "手性分子与对映异构体",
    "新能源开发": "能源利用与新能源开发",
    "芳香族聚酰胺（芳纶）": "芳香族聚酰胺（芳纶）的特性与应用",
    "基本反应类型": "四大基本反应类型与氧化还原反应的关系",
    "核酸的生物功能": "核酸的生物功能与遗传信息",
    "电池性能评价": "电池性能评价指标",
    "羧酸的酸性": "羧酸的酸性与断键机理",
    "加成聚合反应": "加成聚合反应（加聚反应）",
    "葡萄糖的结构": "葡萄糖的结构与检验方法",
    "过氧化钠的性质": "氧化钠与过氧化钠的性质对比",
    "核酸的分类": "核酸的分类与功能",
    "阿司匹林的合成": "阿司匹林的合成与性质",
    "烯烃的化学性质": "烯烃的化学性质：加成、氧化与加聚",
    "α-氨基酸": "α-氨基酸的结构与手性",
    "Mg-AgCl海水激活电池": "Mg-AgCl海水激活电池的反应原理",
    "可逆反应": "可逆反应与化学平衡状态",
    "转化率": "化学反应的限度与转化率",
    "浓硫酸的吸水性": "浓硫酸的吸水性与脱水性",
    "Fe3+的检验": "Fe3+的检验方法",
    "原子光谱": "基态与激发态及原子光谱",
    "电子排布式": "基态原子电子排布式",
    "有机化合物分类": "官能团与有机化合物分类",
    "元素周期律初步": "元素周期律",
    "缩合聚合反应": "缩合聚合反应（缩聚反应）",
    "能量变化": "化学反应中能量变化的微观实质",
    "溶度积常数": "溶度积常数（Ksp）及其表达式",
    "乙醇的分子结构": "乙醇的分子结构与烃的衍生物",
    "高分子化合物的结构": "高分子化合物的结构类型与性能关系",
    "聚氯乙烯": "聚氯乙烯（PVC）的增塑与安全性",
    "酚醛树脂": "酚醛树脂的合成、结构与性质",
    "有机化合物中的共价键": "共价键",
    "淀粉的物理性质": "淀粉的物理性质与检验",
    "电冶金原理": "电冶金原理：活泼金属冶炼",
    "碰撞理论": "碰撞理论对速率影响因素的解释",
    "电解池的工作原理": "电解池的工作原理与离子迁移",
    "热化学方程式的书写与含义": "热化学方程式的书写",
    "可持续发展": "资源开发中的环境保护与可持续发展",
    "环境保护": "资源开发中的环境保护与可持续发展",
    "绿色化学理念": "绿色化学的核心原则与目标",
    "化学反应限度": "化学反应的限度与转化率",
    "酯化反应": "酯化反应机理与同位素示踪",
    "酯的水解": "酯的定义、性质及水解",
    "化学反应类型": "四大基本反应类型与氧化还原反应的关系",
    "分子式确定": "元素定量分析与实验式确定",
    "同分异构体概念辨析": "同分异构现象与同分异构体",
    "氧化还原初步": "氧化还原反应的定义与特征",
    "元素周期表性质递变": "元素性质的周期性变化规律",
    "同主族元素性质递变性": "同主族元素性质递变规律",
    "金属性与非金属性变化": "同周期元素性质的递变规律",
    "元素周期表的应用": "元素周期律的应用与预测",
    "pH概念": "溶液酸碱性与pH的关系",
    "水的离子积": "水的电离及离子积常数",
    "浓度商Q": "浓度商与化学平衡状态的判断",
    "化学键类型判断": "化学键",
    "酰胺键形成": "脂肪族聚酰胺（锦纶）的合成与性质",
    "酰胺化反应": "脂肪族聚酰胺（锦纶）的合成与性质",
    "产率与原子利用率的区别": "原子经济性反应与原子利用率",
    "金属性与非金属性的过渡": "元素周期表中金属与非金属的分区",
    "合金的形成与性质": "合金的定义与性能优势",
    "能级交错": "构造原理的例外情况",
    "反应热的测定": "中和热的测定与计算",
    "氧化物的分类": "酸性氧化物与碱性氧化物",
    "铝与碱反应产物": "铝及氧化铝的两性性质",
    "酸碱反应原理": "酸、碱的本质",
    "化学键性质": "化学键",
    "同系物性质递变": "同系物概念",
    "常见高分子材料的性质": "高分子材料的基本物理特性",
    "高分子的结构特点": "高分子化合物的结构类型与性能关系",
    "亲水基团的作用": "高吸水性树脂的结构与性能",
    "苯环结构稳定性": "苯的化学性质稳定性",
    "乙酸乙酯的性质": "酯的定义、性质及水解",
    "羧基结构": "羧酸与羧酸衍生物的定义及分类",
    "羧基官能团": "羧酸与羧酸衍生物的定义及分类",
    "羟基的性质": "醇的化学性质：取代、消去与氧化反应",
    "醛的性质": "醛类的通性及代表物性质",
    "烯烃的加成反应": "烯烃的化学性质：加成、氧化与加聚",
    "甲烷的结构": "烷烃的结构特征",
    "乙烷结构": "烷烃的结构特征",
    "甲烷与氯气的反应": "烷烃的化学性质",
    "多肽的形成": "成肽反应与肽键",
    "氨基酸的结构与性质": "α-氨基酸的结构与手性",
    "多糖的结构通式": "淀粉与纤维素的结构及水解",
    "二糖结构": "糖类的定义与分类",
    "有机合成化学": "有机合成的主要任务",
    "拟除虫菊酯": "农药的发展与分类",
    "有机磷农药": "农药的发展与分类",
    "农药毒性评估": "农药对生态环境的影响",
    "化肥的合理施用": "化肥合理施用的原则与危害",
    "农药的合理使用": "农药的安全使用与储存",
    "汽车尾气处理": "大气污染物的来源与次生污染",
    "清洁能源替代": "能源利用与新能源开发",
    "酸雨的形成机制": "酸雨的成因及防治",
    "氮氧化物性质": "一氧化氮和二氧化氮的性质及转化",
    "氢能利用": "能源利用与新能源开发",
    "可持续发展战略": "资源开发中的环境保护与可持续发展",
    "环境保护意识": "资源开发中的环境保护与可持续发展",
    "绿色化学原则": "绿色化学的核心原则与目标",
    "工业污染物": "大气污染物的来源与次生污染",
}

RELATION_SUFFIXES = (
    "的定义与特征",
    "的基本概念",
    "的基本内容",
    "的基本原理",
    "的工作原理",
    "的定义",
    "的概念",
    "的实质",
    "的规律",
    "及其应用",
    "基本概念",
    "基本内容",
    "基本原理",
    "工作原理",
    "概念",
    "规律",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [
            json.loads(line, object_pairs_hook=reject_duplicate_keys)
            for line in handle
            if line.strip()
        ]


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate object keys instead of silently keeping the last value."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json_config(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )


def format_jsonl(records: Iterable[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def unique(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def normalize_label_key(text: str) -> str:
    """Normalize a relation label without changing its chemistry meaning."""
    return re.sub(r"[\s，。；：、（）()《》“”\"'·\-—_]+", "", text or "")


def label_variants(text: str) -> set[str]:
    """Return exact and conservative suffix-stripped lookup keys."""
    base = normalize_label_key(text)
    variants = {base} if base else set()
    for suffix in RELATION_SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix):
            variants.add(base[: -len(suffix)])
    return variants


def source_fingerprint(*records: dict[str, Any]) -> str:
    payload = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[。！？；;])\s*", text or "")
        if part.strip()
    ]


def factual_sentences(text: str) -> list[str]:
    return [
        sentence
        for sentence in sentences(text)
        if not TEACHER_META_RE.search(sentence)
        and not LEADING_LABEL_RE.match(sentence)
    ]


def clean_text(text: str) -> str:
    """Remove presentation artifacts without changing the chemistry claim."""
    value = str(text or "").translate(TRADITIONAL_TEXT_TRANSLATION)
    value = re.sub(r"\s+", " ", value).strip()
    value = LEADING_LABEL_RE.sub("", value)
    value = re.sub(r"\s*([，。；：、])\s*", r"\1", value)
    return value.strip()


def sentence_key(text: str) -> str:
    return normalize_label_key(text).rstrip("。；;")


def strip_terminal_punctuation(text: str) -> str:
    return PUNCTUATION_RE.sub("", clean_text(text)).strip()


def student_scope_text(scope: str) -> str:
    """Keep scope useful to a student, not the textbook-editorial frame."""
    value = strip_terminal_punctuation(scope)
    if not value or STUDENT_SCOPE_META_RE.search(value):
        return ""
    value = re.sub(r"^(?:主要)?(?:适用于|用于|涵盖|包括)\s*", "", value)
    value = re.sub(r"重点(涵盖|介绍|讲解|在于)", r"\1", value)
    return value


def infer_scope_text(
    name: str,
    concept_type: str,
    subtopics: Iterable[str],
) -> tuple[str, bool]:
    """Build a concept-specific scope when the source has no usable scope."""
    topic_items = unique(
        strip_terminal_punctuation(item)
        for item in subtopics
        if str(item).strip()
    )[:4]
    template = SCOPE_INFERENCE_TEMPLATES.get(
        concept_type,
        "围绕{name}的定义、条件和典型表现",
    )
    prefix = template.format(name=name)
    if not topic_items:
        return f"{prefix}。", True
    return f"{prefix}；包括{'、'.join(topic_items)}。", False


def clean_sentences(items: Iterable[str], limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = clean_text(item)
        key = sentence_key(value)
        if not key or key in seen or TEACHER_META_RE.search(value):
            continue
        seen.add(key)
        result.append(value)
        if limit is not None and len(result) >= limit:
            break
    return result


def remove_redundant_boundary(
    items: Iterable[str],
    statement: str,
    scope: str,
) -> list[str]:
    """Keep boundary statements that add information beyond definition/scope."""
    statement_key = sentence_key(statement)
    scope_key = sentence_key(scope)
    result: list[str] = []
    for item in clean_sentences(items):
        key = sentence_key(item)
        if not key:
            continue
        if key == statement_key or key == scope_key:
            continue
        if statement_key and (key.startswith(statement_key) or statement_key.startswith(key)):
            continue
        if scope_key and (key.startswith(scope_key) or scope_key.startswith(key)):
            continue
        result.append(strip_terminal_punctuation(item))
    return unique(result)


def compose_student_explanation(
    statement: str,
    scope: str,
    conditions: Iterable[str],
    exceptions: Iterable[str],
) -> str:
    """Build a student-facing explanation without classroom meta-language."""
    parts = [clean_text(statement)]
    statement_key = sentence_key(parts[0])
    scope_clean = student_scope_text(scope)
    if scope_clean and sentence_key(scope_clean) not in statement_key:
        parts.append(f"适用范围：{scope_clean}")
    condition_items = remove_redundant_boundary(conditions, statement, scope)[:3]
    if condition_items:
        parts.append("适用条件：" + "；".join(strip_terminal_punctuation(item) for item in condition_items))
    condition_keys = {sentence_key(item) for item in condition_items}
    exception_items = [
        item
        for item in remove_redundant_boundary(exceptions, statement, scope)
        if sentence_key(item) not in condition_keys
    ][:3]
    if exception_items:
        parts.append("例外与边界：" + "；".join(strip_terminal_punctuation(item) for item in exception_items))
    return " ".join(part for part in parts if part)


def concept_id(name: str) -> str:
    normalized = re.sub(r"\s+", "", name)
    return "chem_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def stable_id(prefix: str, payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def is_valid_formula(token: str) -> bool:
    if token in ACRONYMS:
        return False
    elements = re.findall(r"[A-Z][a-z]?", token)
    if not elements or any(element not in ELEMENTS for element in elements):
        return False
    if len(elements) == 1 and any(char.isdigit() for char in token):
        return token in {"H2", "N2", "O2", "F2", "Cl2", "Br2", "I2", "O3", "C60", "C70"}
    return len(token) >= 2 and (
        len(elements) >= 2 or any(char.isdigit() for char in token) or "(" in token
    )


def extract_formulas(text: str) -> list[str]:
    normalized = text.translate(SUBSCRIPT_TRANSLATION).translate(SUPERSCRIPT_TRANSLATION)
    result = []
    for match in FORMULA_RE.finditer(normalized):
        token = match.group(1)
        if token in INVALID_FORMULA_TOKENS or token.startswith("("):
            continue
        if not is_valid_formula(token):
            continue
        after = normalized[match.end() : match.end() + 3]
        before = normalized[max(0, match.start() - 1) : match.start()]
        if before in {"-", "—", "–"}:
            continue
        if re.match(r"(?:\d*[+\-]|\^)", after):
            continue
        result.append(token)
    return unique(result)


def extract_equations(text: str) -> list[str]:
    result = []
    for sentence in sentences(text):
        if not EQUATION_RE.search(sentence):
            continue
        if extract_formulas(sentence) or re.search(r"pH|K(?:sp|a|b|w|c)|Δ[HSG]", sentence):
            result.append(sentence)
    return unique(result)


def extract_notations(text: str) -> list[str]:
    return unique(match.group(0) for match in SPECIAL_FORMULA_RE.finditer(text))


def extract_facts(core: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return factual core ideas, conditions, exceptions and examples."""
    ideas = clean_sentences(factual_sentences(core))
    conditions = [sentence for sentence in ideas if CONDITION_RE.search(sentence)]
    exceptions = [sentence for sentence in ideas if EXCEPTION_RE.search(sentence)]
    examples = [
        sentence
        for sentence in ideas
        if EXAMPLE_RE.search(sentence)
        and not sentence.startswith(("适用范围", "适用条件", "边界", "注意"))
    ]
    return (
        unique(ideas),
        clean_sentences(conditions),
        clean_sentences(exceptions),
        clean_sentences(examples),
    )


def extract_boundary_notes(
    core: str,
    statement: str,
    scope: str,
    conditions: Iterable[str],
    exceptions: Iterable[str],
) -> list[str]:
    """Keep distinct boundary statements out of the definition/scope fields."""
    exclusion_keys = {
        sentence_key(statement),
        sentence_key(scope),
        *(sentence_key(item) for item in conditions),
        *(sentence_key(item) for item in exceptions),
    }
    result = []
    for sentence in clean_sentences(factual_sentences(core)):
        key = sentence_key(sentence)
        if not key or key in exclusion_keys:
            continue
        if not BOUNDARY_RE.search(sentence):
            continue
        if any(key.startswith(other) or other.startswith(key) for other in exclusion_keys if other):
            continue
        result.append(strip_terminal_punctuation(sentence))
    return unique(result)


def apply_content_override(concept: dict[str, Any], override: dict[str, Any]) -> None:
    """Apply a reviewed concept-level correction without changing provenance."""
    definition_override = override.get("definition", {})
    for field in ("statement", "scope"):
        if field in definition_override:
            concept["definition"][field] = clean_text(definition_override[field])
    for field in ("conditions", "exceptions", "boundary_notes"):
        if field in definition_override:
            concept["definition"][field] = unique(
                strip_terminal_punctuation(item)
                for item in definition_override[field]
                if str(item).strip()
            )
    if "scope" in definition_override:
        concept["quality"]["issue_details"] = [
            detail
            for detail in concept["quality"]["issue_details"]
            if detail.get("code") not in SCOPE_ISSUE_CODES
        ]
        concept["quality"]["open_issues"] = [
            issue
            for issue in concept["quality"]["open_issues"]
            if "scope" not in issue.lower() and "适用范围" not in issue
        ]
    if override.get("subtopics") is not None:
        concept["subtopics"] = unique(override["subtopics"])
    if override.get("core_ideas") is not None:
        concept["core_ideas"] = unique(
            clean_text(item)
            for item in override["core_ideas"]
            if str(item).strip()
        )
    if override.get("teaching_sequence") is not None:
        concept["teaching"]["teaching_sequence"] = unique(
            clean_text(item)
            for item in override["teaching_sequence"]
            if str(item).strip()
        )
    if override.get("analogy") is not None:
        analogy = override["analogy"]
        concept["teaching"]["analogy"] = {
            "text": clean_text(analogy.get("text", "")),
            "limitations": clean_text(
                analogy.get(
                    "limitations",
                    concept["teaching"]["analogy"].get("limitations", ""),
                )
            ),
        }
    if override.get("concept_type"):
        concept["concept_type"] = override["concept_type"]
    if override.get("student_explanation"):
        concept["teaching"]["student_explanation"] = clean_text(
            override["student_explanation"]
        )
    elif any(
        field in definition_override
        for field in ("statement", "scope", "conditions", "exceptions", "boundary_notes")
    ):
        concept["teaching"]["student_explanation"] = compose_student_explanation(
            concept["definition"]["statement"],
            concept["definition"]["scope"],
            concept["definition"]["conditions"],
            concept["definition"]["exceptions"],
        )
    if override.get("teacher_notes") is not None:
        concept["teaching"]["teacher_notes"] = unique(override["teacher_notes"])
    if override.get("examples") is not None:
        concept["examples"] = unique(override["examples"])
    if override.get("non_examples") is not None:
        concept["non_examples"] = unique(override["non_examples"])
    if override.get("correction"):
        concept["quality"]["corrections"].append(
            f"C1 canonical content correction: {override['correction']}"
        )
        concept["provenance"]["definition_origin"] = "canonical_content_override"


def infer_concept_type(name: str, statement: str) -> str:
    text = f"{name} {statement}"
    if re.search(r"安全|危险|事故|废弃物|GHS|防护|应急处置", name):
        return "safety"
    if re.search(r"历史|发展史|科学价值|科学家|门捷列夫|职业", name):
        return "history"
    if re.search(r"表示方法|化学式|电子式|结构式|键线式|符号|书写规范|命名规则", name):
        return "representation"
    if re.search(
        r"检验|测定|制备|合成|分离|提纯|滴定|书写|计算|实验(?!式)|操作|方法|技术|冶炼|提取|推断|鉴别",
        name,
    ):
        return "method"
    if re.search(
        r"性质|物理性质|化学性质|颜色|气味|密度|熔沸点|溶解性|导电性|稳定性|毒性",
        name,
    ):
        return "property"
    if re.search(
        r"化学键|离子键|共价键|分子间作用力|氢键|元素周期律|原子结构|晶体|杂化|"
        r"糖类的定义|糖类的分类|糖类的结构|淀粉与纤维素",
        name,
    ):
        return "core_concept"
    if re.search(r"反应|平衡|电离|水解|腐蚀|聚合|缩聚|加聚|氧化|还原|转化|循环|机理|能量", text):
        return "process"
    if re.search(r"DNA|RNA|核酸|蛋白质|酶|糖类|ATP|生命|医学|生物", text):
        return "cross_disciplinary"
    if re.search(r"应用|用途|危害|影响|意义|价值|环境保护|资源|可持续发展|材料|生产", text):
        return "application"
    return "core_concept"


def select_primary(
    records: list[dict[str, Any]], corrected: set[str]
) -> dict[str, Any]:
    return max(
        records,
        key=lambda record: (
            record["kp_id"] in corrected,
            float(record.get("confidence", 0)),
            len(record.get("definition_summary", "")),
            len(record.get("teacher_explanation", {}).get("core_explanation", "")),
        ),
    )


def build_groups(
    explicit_by_book: dict[str, list[dict[str, Any]]],
    group_payload: dict[str, Any],
    occurrence_order: dict[str, int],
) -> list[dict[str, Any]]:
    explicit_by_id = {
        record["kp_id"]: record
        for records in explicit_by_book.values()
        for record in records
    }
    groups: list[dict[str, Any]] = []
    assigned: set[str] = set()

    for item in group_payload["groups"]:
        member_ids = list(item["kp_ids"])
        missing = [kp_id for kp_id in member_ids if kp_id not in explicit_by_id]
        if missing:
            raise ValueError(f"Canonical group has missing occurrences: {missing}")
        overlap = assigned.intersection(member_ids)
        if overlap:
            raise ValueError(f"Occurrence assigned to multiple canonical groups: {sorted(overlap)}")
        assigned.update(member_ids)
        groups.append(
            {
                "canonical_name": item["canonical_name"],
                "kp_ids": member_ids,
                "definition_override": item.get("definition"),
            }
        )

    ungrouped: OrderedDict[str, list[str]] = OrderedDict()
    for records in explicit_by_book.values():
        for record in records:
            kp_id = record["kp_id"]
            if kp_id in assigned:
                continue
            normalized_name = re.sub(r"\s+", "", record["name"])
            ungrouped.setdefault(normalized_name, []).append(kp_id)
    for member_ids in ungrouped.values():
        groups.append(
            {
                "canonical_name": explicit_by_id[member_ids[0]]["name"],
                "kp_ids": member_ids,
                "definition_override": None,
            }
        )

    groups.sort(key=lambda group: min(occurrence_order[kp_id] for kp_id in group["kp_ids"]))
    return groups


def load_overrides(path: Path) -> tuple[dict[str, Any], set[str]]:
    payload = load_json_config(path)
    return payload["overrides"], set(payload["overrides"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    manifest = load_json_config(DATA_DIR / "manifest.json")
    book_rows = manifest["books"]
    book_ids = [book["book_id"] for book in book_rows]

    explicit_by_book: dict[str, list[dict[str, Any]]] = {}
    teaching_by_book: dict[str, list[dict[str, Any]]] = {}
    explicit_by_id: dict[str, dict[str, Any]] = {}
    teaching_by_id: dict[str, dict[str, Any]] = {}
    book_meta: dict[str, dict[str, Any]] = {}
    occurrence_order: dict[str, int] = {}
    occurrence_rows: list[dict[str, Any]] = []

    for book in book_rows:
        book_id = book["book_id"]
        explicit = read_jsonl(DATA_DIR / "explicit" / f"{book_id}.explicit.jsonl")
        teaching = read_jsonl(DATA_DIR / "teaching" / f"{book_id}.teaching.jsonl")
        explicit_by_book[book_id] = explicit
        teaching_by_book[book_id] = teaching
        book_meta[book_id] = book
        explicit_ids = {record["kp_id"] for record in explicit}
        teaching_ids = {record["kp_id"] for record in teaching}
        if explicit_ids != teaching_ids:
            raise ValueError(f"{book_id}: explicit and teaching kp_id sets differ")
        for record in explicit:
            explicit_by_id[record["kp_id"]] = record
        for record in teaching:
            teaching_by_id[record["kp_id"]] = record
        for record in explicit:
            occurrence_order[record["kp_id"]] = len(occurrence_order)

    p0_overrides, p0_ids = load_overrides(P0_PATH)
    p1_overrides, p1_ids = load_overrides(P1_PATH)
    p2_overrides, p2_ids = load_overrides(P2_PATH)
    corrected_ids = p0_ids | p1_ids | p2_ids
    external_priors = load_json_config(EXTERNAL_PRIOR_PATH)["labels"]
    group_payload = load_json_config(GROUPS_PATH)
    content_override_payload = load_json_config(CONTENT_OVERRIDES_PATH)
    content_overrides = content_override_payload.get("overrides", {})
    confusable_payload = load_json_config(CONFUSABLE_PAIRS_PATH)
    groups = build_groups(explicit_by_book, group_payload, occurrence_order)

    canonical_names_seen: set[str] = set()
    concept_groups: list[dict[str, Any]] = []
    kp_to_group: dict[str, dict[str, Any]] = {}
    for group in groups:
        name = group["canonical_name"]
        if name in canonical_names_seen:
            raise ValueError(f"Duplicate canonical name: {name}")
        canonical_names_seen.add(name)
        group["concept_id"] = concept_id(name)
        concept_groups.append(group)
        for kp_id in group["kp_ids"]:
            kp_to_group[kp_id] = group

    concept_ids = [group["concept_id"] for group in concept_groups]
    if len(concept_ids) != len(set(concept_ids)):
        raise ValueError("Duplicate concept_id generated")

    raw_relations: list[dict[str, Any]] = []
    concepts: list[dict[str, Any]] = []
    for group in concept_groups:
        member_ids = group["kp_ids"]
        explicit_records = [explicit_by_id[kp_id] for kp_id in member_ids]
        teaching_records = [teaching_by_id[kp_id] for kp_id in member_ids]
        primary_explicit = select_primary(explicit_records, corrected_ids)
        primary_teaching = teaching_by_id[primary_explicit["kp_id"]]
        statement = clean_text(
            group["definition_override"] or primary_explicit["definition_summary"]
        )
        concept_type = infer_concept_type(group["canonical_name"], statement)
        core = primary_teaching["teacher_explanation"]["core_explanation"]
        subtopics = unique(
            item for record in explicit_records for item in record.get("sub_points", [])
        )
        scope_candidates = [
            record.get("textbook_scope", "").strip()
            for record in explicit_records
            if record.get("textbook_scope", "").strip()
        ]
        raw_scope = clean_text(max(scope_candidates, key=len)) if scope_candidates else ""
        scope = student_scope_text(raw_scope)
        scope_inferred = False
        scope_generic = False
        if not scope:
            scope, scope_generic = infer_scope_text(
                group["canonical_name"],
                concept_type,
                subtopics,
            )
            scope_inferred = True
        factual, conditions, exceptions, examples = extract_facts(
            f"{statement}。{core}"
        )
        statement_key = sentence_key(statement)
        core_ideas = [
            sentence
            for sentence in factual
            if sentence_key(sentence) != statement_key
            and sentence_key(sentence) != sentence_key(scope)
        ]
        conditions = remove_redundant_boundary(conditions, statement, scope)
        exceptions = remove_redundant_boundary(exceptions, statement, scope)
        examples = clean_sentences(examples)
        boundary_notes = extract_boundary_notes(
            core, statement, scope, conditions, exceptions
        )
        formulas = extract_formulas(
            "\n".join(
                [statement, core]
                + [
                    item.get("correction", "")
                    for record in teaching_records
                    for item in record.get("student_misconceptions", [])
                ]
            )
        )
        equations = extract_equations(f"{statement}\n{core}")
        notations = extract_notations(f"{statement}\n{core}")
        issues: list[str] = []
        if formulas:
            issues.append("formulas are machine-extracted from prose; not validated")
        if equations:
            issues.append(
                "equations are prose-extracted; stoichiometry, charge and conditions are not validated"
            )
        if conditions or exceptions or examples:
            issues.append(
                "conditions, exceptions or examples are machine-extracted; expert review required"
            )
        if scope_inferred:
            issues.append(
                "scope was inferred from source structure and requires expert confirmation"
            )
        issue_details: list[dict[str, Any]] = []
        if formulas:
            issue_details.append(
                {
                    "code": "formula_extraction_unverified",
                    "severity": "review",
                    "message": "formulas are machine-extracted from prose; not validated",
                }
            )
        if equations:
            issue_details.append(
                {
                    "code": "equation_extraction_unverified",
                    "severity": "review",
                    "message": "equations are prose-extracted; stoichiometry, charge and conditions are not validated",
                }
            )
        if conditions or exceptions or examples:
            issue_details.append(
                {
                    "code": "boundary_extraction_unverified",
                    "severity": "review",
                    "message": "conditions, exceptions or examples are machine-extracted; expert review required",
                }
            )
        if scope_inferred:
            issue_details.append(
                {
                    "code": (
                        "scope_generic"
                        if scope_generic
                        else "scope_inferred_from_subtopics"
                    ),
                    "severity": "review",
                    "message": (
                        "scope was inferred from concept type because no specific subtopics were available; expert review required"
                        if scope_generic
                        else "scope was inferred from source subtopics; expert review required"
                    ),
                }
            )

        name_aliases = [
            record["name"] for record in explicit_records
        ] + [
            alias for record in explicit_records for alias in record.get("aliases", [])
        ]
        aliases = [
            alias
            for alias in unique(name_aliases)
            if alias != group["canonical_name"]
        ]
        misconceptions = []
        misconception_seen: set[tuple[str, str]] = set()
        for record in teaching_records:
            for item in record.get("student_misconceptions", []):
                misconception_statement = item.get("misconception", "").strip()
                misconception_correction = item.get("correction", "").strip()
                if not misconception_statement or not misconception_correction:
                    issues.append(
                        f"incomplete misconception omitted: {record['kp_id']}"
                    )
                    continue
                key = (misconception_statement, misconception_correction)
                if key not in misconception_seen:
                    misconception_seen.add(key)
                    misconceptions.append(
                        {
                            "statement": misconception_statement,
                            "correction": misconception_correction,
                            "source_occurrence_ids": [record["kp_id"]],
                        }
                    )
        non_examples = unique(
            f"错误认识：{item['statement']}"
            for item in misconceptions
            if item.get("statement")
        )[:8]
        assessment_types = unique(
            item
            for record in teaching_records
            for item in record.get("exam_usage", {}).get("common_question_types", [])
        )
        assessment_traps = unique(
            item
            for record in teaching_records
            for item in record.get("exam_usage", {}).get("typical_traps", [])
        )
        practice_hints = unique(
            item
            for record in teaching_records
            for item in record.get("practice_generation_hints", [])
        )
        difficulty_counts = Counter(
            {"易": "easy", "中": "medium", "难": "hard"}.get(
                record.get("exam_usage", {}).get("difficulty"), "medium"
            )
            for record in teaching_records
        )
        difficulty = difficulty_counts.most_common(1)[0][0]
        sequences = unique(
            item
            for record in teaching_records
            for item in record["teacher_explanation"].get("teaching_sequence", [])
        )
        primary_core = primary_teaching["teacher_explanation"]["core_explanation"]
        primary_analogy = primary_teaching["teacher_explanation"].get("classroom_analogy", "")
        evidence_summaries = clean_sentences(
            record.get("text_evidence_summary", "")
            for record in explicit_records
            if record.get("text_evidence_summary")
        )

        provenance_refs = []
        seen_refs: set[str] = set()
        for record in explicit_records:
            for ref in record.get("textbook_refs", []):
                key = json.dumps(ref, ensure_ascii=False, sort_keys=True)
                if key not in seen_refs:
                    seen_refs.add(key)
                    provenance_refs.append(ref)

        flags = unique(
            flag for record in list(explicit_records) + list(teaching_records)
            for flag in record.get("quality_flags", [])
        )
        corrections = []
        for kp_id in member_ids:
            if kp_id in p0_ids:
                corrections.append(f"P0 content correction: {kp_id}")
            if kp_id in p1_ids:
                corrections.append(f"P1 content correction: {kp_id}")
            if kp_id in p2_ids:
                corrections.append(f"P2 consistency correction: {kp_id}")

        relation_fields = {
            "prerequisites": "prerequisites",
            "related": "related_points",
        }
        for relation_type, source_field in relation_fields.items():
            for record in explicit_records:
                for label in record.get(source_field, []):
                    raw_relations.append(
                        {
                            "source_concept_id": group["concept_id"],
                            "source_occurrence_id": record["kp_id"],
                            "relation_type": relation_type,
                            "target_label": label.strip(),
                        }
                    )

        concept = {
            "schema_version": "chem-concept-v1",
            "concept_id": group["concept_id"],
            "canonical_name": group["canonical_name"],
            "subject": "chemistry",
            "curriculum": {
                "level": "high_school",
                "module": primary_explicit["textbook_refs"][0]["book_title"],
                "grade_band": "compulsory" if primary_explicit["textbook_refs"][0]["book_id"] in {"tb_bx1", "tb_bx2"} else "elective",
            },
            "concept_type": concept_type,
            "aliases": aliases,
            "subtopics": subtopics,
            "definition": {
                "statement": statement,
                "scope": scope,
                "conditions": clean_sentences(conditions, limit=8),
                "exceptions": clean_sentences(exceptions, limit=8),
                "boundary_notes": boundary_notes[:8],
            },
            "core_ideas": core_ideas[:8],
            "representations": {
                "formulas": formulas,
                "equations": equations,
                "notations": notations,
            },
            "examples": examples[:8],
            "non_examples": non_examples,
            "relations": {
                "prerequisites": [],
                "related": [],
                "confusable": [],
            },
            "teaching": {
                "student_explanation": compose_student_explanation(
                    statement,
                    scope,
                    conditions,
                    exceptions,
                ),
                "teacher_notes": unique([primary_core] + evidence_summaries[:1]),
                "teaching_sequence": sequences,
                "analogy": {
                    "text": primary_analogy,
                    "limitations": "类比只用于建立直观印象，不能替代定义、适用条件、例外和证据。",
                },
            },
            "misconceptions": misconceptions,
            "assessment": {
                "common_question_types": assessment_types,
                "typical_traps": assessment_traps,
                "practice_generation_hints": practice_hints,
                "difficulty": difficulty,
            },
            "provenance": {
                "occurrence_ids": member_ids,
                "primary_explicit_occurrence_id": primary_explicit["kp_id"],
                "primary_teaching_occurrence_id": primary_teaching["kp_id"],
                "definition_origin": (
                    "canonical_group_override"
                    if group["definition_override"]
                    else "explicit_definition"
                ),
                "evidence_status": "ai_textbook_summary_unverified",
                "source_fingerprint": source_fingerprint(
                    *[
                        record
                        for kp_id in member_ids
                        for record in (explicit_by_id[kp_id], teaching_by_id[kp_id])
                    ]
                ),
                "books": unique(
                    record["textbook_refs"][0]["book_title"] for record in explicit_records
                ),
                "chapters": unique(
                    ref["chapter"]
                    for record in explicit_records
                    for ref in record.get("textbook_refs", [])
                ),
                "textbook_refs": provenance_refs,
            },
            "quality": {
                "review_status": "machine_reviewed",
                "human_verified": False,
                "confidence": round(
                    min(float(record.get("confidence", 0)) for record in explicit_records),
                    3,
                ),
                "quality_flags": flags,
                "corrections": corrections,
                "open_issues": unique(issues),
                "issue_details": issue_details,
                "evidence_status": "ai_textbook_summary_unverified",
            },
        }
        content_override = content_overrides.get(concept["canonical_name"])
        if content_override:
            apply_content_override(concept, content_override)
        concepts.append(concept)

    unknown_override_names = sorted(set(content_overrides) - canonical_names_seen)
    if unknown_override_names:
        raise ValueError(
            f"Canonical content overrides reference unknown concepts: {unknown_override_names}"
        )

    # Curated contrast pairs are kept outside the free-text misconception
    # fields so a downstream tutor can retrieve an explicit, symmetric
    # "what exactly is different" record.
    concept_by_name = {concept["canonical_name"]: concept for concept in concepts}
    confusable_rows: list[dict[str, Any]] = []
    seen_confusable_pairs: set[tuple[str, str]] = set()
    for pair in confusable_payload["pairs"]:
        left_name = str(pair["left"]).strip()
        right_name = str(pair["right"]).strip()
        left = concept_by_name.get(left_name)
        right = concept_by_name.get(right_name)
        if left is None or right is None:
            missing = [
                name
                for name, concept in ((left_name, left), (right_name, right))
                if concept is None
            ]
            raise ValueError(
                f"Confusable pair references unknown concepts: {missing}"
            )
        if left["concept_id"] == right["concept_id"]:
            raise ValueError(f"Confusable pair is self-referential: {left_name}")
        pair_key = tuple(sorted((left["concept_id"], right["concept_id"])))
        if pair_key in seen_confusable_pairs:
            raise ValueError(f"Duplicate confusable pair: {left_name} / {right_name}")
        seen_confusable_pairs.add(pair_key)
        dimensions = unique(pair.get("dimensions", []))
        distinction = clean_text(pair.get("distinction", ""))
        if not dimensions or not distinction:
            raise ValueError(f"Confusable pair lacks dimensions or distinction: {left_name} / {right_name}")
        left["relations"]["confusable"].append(right["concept_id"])
        right["relations"]["confusable"].append(left["concept_id"])
        confusable_rows.append(
            {
                "schema_version": "chem-confusable-pair-v1",
                "pair_id": stable_id("cmp_", pair_key),
                "left_concept_id": left["concept_id"],
                "left_name": left_name,
                "right_concept_id": right["concept_id"],
                "right_name": right_name,
                "dimensions": dimensions,
                "distinction": distinction,
                "review_status": "machine_reviewed",
                "human_verified": False,
                "evidence_status": "ai_textbook_summary_unverified",
            }
        )

    # Alias uniqueness is a data contract: an alias must not point at another
    # canonical concept or at a second concept with the same name.
    canonical_owner = {
        concept["canonical_name"]: concept["concept_id"] for concept in concepts
    }
    alias_owners: dict[str, set[str]] = defaultdict(set)
    for concept in concepts:
        for alias in concept["aliases"]:
            alias_owners[alias].add(concept["concept_id"])
    ambiguous_aliases = {
        alias: sorted(owners)
        for alias, owners in alias_owners.items()
        if len(owners) > 1
        or (alias in canonical_owner and canonical_owner[alias] not in owners)
    }
    for concept in concepts:
        original_aliases = list(concept["aliases"])
        concept["aliases"] = [
            alias for alias in original_aliases if alias not in ambiguous_aliases
        ]
        concept["quality"]["open_issues"].extend(
            f"ambiguous alias omitted: {alias}"
            for alias in original_aliases
            if alias in ambiguous_aliases
        )
        concept["quality"]["issue_details"].extend(
            {
                "code": "ambiguous_alias_omitted",
                "severity": "review",
                "message": f"ambiguous alias omitted: {alias}",
            }
            for alias in original_aliases
            if alias in ambiguous_aliases
        )
        concept["quality"]["open_issues"] = unique(
            concept["quality"]["open_issues"]
        )

    exact_lookup: dict[str, set[str]] = defaultdict(set)
    normalized_lookup: dict[str, set[str]] = defaultdict(set)

    def add_lookup(text: str, target_id: str) -> None:
        if not text:
            return
        exact_lookup[text].add(target_id)
        for variant in label_variants(text):
            normalized_lookup[variant].add(target_id)

    for concept in concepts:
        add_lookup(concept["canonical_name"], concept["concept_id"])
        for alias in concept["aliases"]:
            add_lookup(alias, concept["concept_id"])

    def resolve_relation_label(label: str) -> tuple[set[str], str, str]:
        manual_target_name = RELATION_LABEL_ALIASES.get(label)
        if label in exact_lookup:
            return exact_lookup[label], "exact_label", ""
        exact_candidates: set[str] = set()
        for variant in sorted(label_variants(label)):
            exact_candidates.update(exact_lookup.get(variant, set()))
        if exact_candidates:
            return exact_candidates, "exact_label_normalized", ""
        if manual_target_name:
            if manual_target_name in canonical_owner:
                return {canonical_owner[manual_target_name]}, "manual_label_map", ""
            manual_candidates: set[str] = set()
            for variant in sorted(label_variants(manual_target_name)):
                manual_candidates.update(normalized_lookup.get(variant, set()))
            if manual_candidates:
                return manual_candidates, "manual_label_map", ""
        normalized_candidates: set[str] = set()
        for variant in sorted(label_variants(label)):
            normalized_candidates.update(normalized_lookup.get(variant, set()))
        if normalized_candidates:
            return normalized_candidates, "normalized_label", ""
        if label in external_priors:
            return set(), "external_prior", external_priors[label]
        return set(), "none", ""

    # Resolve relation labels only when they map to exactly one concept.
    relation_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unresolved_counts: Counter[str] = Counter()
    for relation in raw_relations:
        label = relation["target_label"]
        candidates, resolution_method, resolution_note = resolve_relation_label(label)
        if len(candidates) == 1:
            target = next(iter(candidates))
            status = "resolved"
            if target == relation["source_concept_id"]:
                status = "self_reference"
        elif len(candidates) > 1:
            target = None
            status = "ambiguous"
            unresolved_counts["ambiguous"] += 1
        elif resolution_method == "external_prior":
            target = None
            status = "external_prior"
            unresolved_counts["external_prior"] += 1
        else:
            target = None
            status = "unresolved"
            unresolved_counts["unresolved"] += 1
        resolved = dict(relation)
        resolved["target_concept_id"] = target
        resolved["target_candidates"] = sorted(candidates) if len(candidates) > 1 else []
        resolved["resolution_status"] = status
        resolved["resolution_method"] = resolution_method
        resolved["resolution_note"] = resolution_note
        resolved["relation_id"] = stable_id(
            "rel_",
            [
                relation["source_concept_id"],
                relation["source_occurrence_id"],
                relation["relation_type"],
                label,
            ],
        )
        relation_by_source[relation["source_concept_id"]].append(resolved)

    for concept in concepts:
        unresolved_relations: list[tuple[str, str]] = []
        external_relations: list[str] = []
        self_reference_labels = []
        for relation in relation_by_source[concept["concept_id"]]:
            if relation["resolution_status"] == "resolved":
                bucket = concept["relations"][relation["relation_type"]]
                if relation["target_concept_id"] not in bucket:
                    bucket.append(relation["target_concept_id"])
            elif relation["resolution_status"] == "self_reference":
                self_reference_labels.append(relation["target_label"])
            elif relation["resolution_status"] == "external_prior":
                external_relations.append(relation["target_label"])
            else:
                unresolved_relations.append(
                    (relation["target_label"], relation["resolution_status"])
                )
        concept["quality"]["open_issues"].extend(
            f"unresolved relation: {label}"
            for label in unique(label for label, _ in unresolved_relations)
        )
        concept["quality"]["issue_details"].extend(
            {
                "code": (
                    "ambiguous_relation"
                    if status == "ambiguous"
                    else "unresolved_relation"
                ),
                "severity": "review",
                "message": f"unresolved relation: {label}",
                "target_label": label,
            }
            for label, status in unresolved_relations
        )
        concept["quality"]["open_issues"].extend(
            f"external prior relation: {label}"
            for label in unique(external_relations)
        )
        concept["quality"]["issue_details"].extend(
            {
                "code": "external_prior_relation",
                "severity": "review",
                "message": f"external prior relation: {label}",
                "target_label": label,
            }
            for label in unique(external_relations)
        )
        concept["quality"]["open_issues"].extend(
            f"self-referential relation omitted: {label}"
            for label in unique(self_reference_labels)
        )
        concept["quality"]["issue_details"].extend(
            {
                "code": "self_referential_relation",
                "severity": "review",
                "message": f"self-referential relation omitted: {label}",
                "target_label": label,
            }
            for label in unique(self_reference_labels)
        )
        concept["quality"]["open_issues"] = unique(
            concept["quality"]["open_issues"]
        )
        detail_seen: set[tuple[str, str, str]] = set()
        unique_details = []
        for detail in concept["quality"]["issue_details"]:
            key = (
                detail.get("code", ""),
                detail.get("message", ""),
                detail.get("target_label", ""),
            )
            if key not in detail_seen:
                detail_seen.add(key)
                unique_details.append(detail)
        concept["quality"]["issue_details"] = unique_details
        concept["relations"]["prerequisites"].sort()
        concept["relations"]["related"].sort()
        concept["relations"]["confusable"].sort()

    # One review-sheet row per canonical concept makes the automated coverage
    # visible without pretending that every concept has been expert-approved.
    review_sheet_rows: list[dict[str, Any]] = []
    for concept in concepts:
        relation_items = relation_by_source.get(concept["concept_id"], [])
        status_counts = Counter(
            item["resolution_status"] for item in relation_items
        )
        field_checks = {
            "definition_present": bool(concept["definition"]["statement"].strip()),
            "scope_present": bool(concept["definition"]["scope"].strip()),
            "scope_specific": not any(
                detail.get("code") in {"scope_generic", "scope_missing"}
                for detail in concept["quality"]["issue_details"]
            ),
            "conditions_or_exceptions_present": bool(
                concept["definition"]["conditions"]
                or concept["definition"]["exceptions"]
                or concept["definition"]["boundary_notes"]
            ),
            "student_explanation_present": bool(
                concept["teaching"]["student_explanation"].strip()
            ),
            "examples_or_non_examples_present": bool(
                concept["examples"] or concept["non_examples"]
            ),
            "misconceptions_present": bool(concept["misconceptions"]),
            "prerequisite_links_present": bool(
                concept["relations"]["prerequisites"]
            ),
            "confusable_links_present": bool(
                concept["relations"]["confusable"]
            ),
            "source_occurrence_coverage": bool(
                concept["provenance"]["occurrence_ids"]
            ),
        }
        missing_checks = sorted(
            name for name, passed in field_checks.items() if not passed
        )
        issue_codes = sorted(
            {detail["code"] for detail in concept["quality"]["issue_details"]}
        )
        if any(
            detail.get("severity") == "blocking"
            for detail in concept["quality"]["issue_details"]
        ) or status_counts["unresolved"] >= 5 or "needs_safety_review" in concept["quality"]["quality_flags"]:
            review_priority = "high"
        elif issue_codes or missing_checks:
            review_priority = "medium"
        else:
            review_priority = "baseline"
        review_sheet_rows.append(
            {
                "schema_version": "chem-review-sheet-v1",
                "concept_id": concept["concept_id"],
                "canonical_name": concept["canonical_name"],
                "concept_type": concept["concept_type"],
                "source_occurrence_count": len(
                    concept["provenance"]["occurrence_ids"]
                ),
                "field_checks": field_checks,
                "missing_field_checks": missing_checks,
                "relation_counts": {
                    "resolved": status_counts["resolved"],
                    "unresolved": status_counts["unresolved"],
                    "external_prior": status_counts["external_prior"],
                    "self_reference": status_counts["self_reference"],
                    "ambiguous": status_counts["ambiguous"],
                },
                "confusable_count": len(concept["relations"]["confusable"]),
                "issue_codes": issue_codes,
                "review_priority": review_priority,
                "review_focus": missing_checks or issue_codes or [
                    "自动字段检查无缺口；仍需教师事实复核"
                ],
                "review_status": "machine_reviewed",
                "human_verified": False,
                "evidence_status": "ai_textbook_summary_unverified",
            }
        )
    review_sheet_rows.sort(key=lambda item: item["concept_id"])

    # Occurrence index is intentionally separate from the canonical concepts.
    for book_id in book_ids:
        for record in explicit_by_book[book_id]:
            group = kp_to_group[record["kp_id"]]
            occurrence_rows.append(
                {
                    "schema_version": "chem-occurrence-v1",
                    "occurrence_id": record["kp_id"],
                    "concept_id": group["concept_id"],
                    "book_id": book_id,
                    "book_title": record["textbook_refs"][0]["book_title"],
                    "original_name": record["name"],
                    "category_path": record.get("category_path", []),
                    "textbook_refs": record.get("textbook_refs", []),
                    "source_level": record.get("source_level"),
                    "review_status": record.get("review_status"),
                    "confidence": record.get("confidence"),
                    "definition_summary": record.get("definition_summary", ""),
                    "textbook_scope": record.get("textbook_scope", ""),
                    "text_evidence_summary": record.get("text_evidence_summary", ""),
                    "source_fingerprint": source_fingerprint(
                        record, teaching_by_id[record["kp_id"]]
                    ),
                    "quality_flags": record.get("quality_flags", []),
                }
            )

    relation_rows = sorted(
        (relation for items in relation_by_source.values() for relation in items),
        key=lambda item: (item["source_concept_id"], item["relation_type"], item["target_label"]),
    )
    concept_name_by_id = {
        concept["concept_id"]: concept["canonical_name"] for concept in concepts
    }
    gap_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relation_rows:
        if relation["resolution_status"] == "resolved":
            continue
        gap_groups[relation["target_label"]].append(relation)
    relation_gap_rows = []
    for label, items in sorted(
        gap_groups.items(), key=lambda item: (-len(item[1]), item[0])
    ):
        candidate_ids = sorted(
            {
                candidate
                for relation in items
                for candidate in relation.get("target_candidates", [])
            }
        )
        relation_gap_rows.append(
            {
                "target_label": label,
                "relation_count": len(items),
                "relation_types": sorted({item["relation_type"] for item in items}),
                "resolution_statuses": sorted(
                    {item["resolution_status"] for item in items}
                ),
                "source_concept_ids": sorted(
                    {item["source_concept_id"] for item in items}
                ),
                "source_concept_names": sorted(
                    {
                        concept_name_by_id.get(item["source_concept_id"], "")
                        for item in items
                        if concept_name_by_id.get(item["source_concept_id"])
                    }
                ),
                "source_occurrence_ids": sorted(
                    {item["source_occurrence_id"] for item in items}
                ),
                "target_candidates": candidate_ids,
                "target_candidate_names": [
                    concept_name_by_id[candidate]
                    for candidate in candidate_ids
                    if candidate in concept_name_by_id
                ],
                "resolution_notes": sorted(
                    {
                        item["resolution_note"]
                        for item in items
                        if item.get("resolution_note")
                    }
                ),
            }
        )

    concepts.sort(key=lambda item: item["concept_id"])
    occurrence_rows.sort(key=lambda item: item["occurrence_id"])
    relation_rows.sort(
        key=lambda item: (item["source_concept_id"], item["relation_type"], item["target_label"])
    )
    confusable_rows.sort(
        key=lambda item: (item["left_name"], item["right_name"])
    )

    review_queue_rows = [
        {
            "concept_id": concept["concept_id"],
            "canonical_name": concept["canonical_name"],
            "open_issues": concept["quality"]["open_issues"],
            "issue_codes": sorted(
                {detail["code"] for detail in concept["quality"]["issue_details"]}
            ),
            "issue_details": concept["quality"]["issue_details"],
            "severity": (
                "blocking"
                if any(
                    detail.get("severity") == "blocking"
                    for detail in concept["quality"]["issue_details"]
                )
                else "review"
            ),
            "quality_flags": concept["quality"]["quality_flags"],
            "confidence": concept["quality"]["confidence"],
            "evidence_status": concept["quality"]["evidence_status"],
            "source_occurrence_ids": concept["provenance"]["occurrence_ids"],
        }
        for concept in concepts
        if concept["quality"]["open_issues"]
    ]
    issue_code_counts = Counter(
        detail["code"]
        for concept in concepts
        for detail in concept["quality"]["issue_details"]
    )
    blocking_concepts = sum(
        1
        for concept in concepts
        if any(
            detail.get("severity") == "blocking"
            for detail in concept["quality"]["issue_details"]
        )
    )

    manifest_out = {
        "schema_version": "chem-model-v1",
        "generated_at": "2026-11-19",
        "source": "data/explicit and data/teaching",
        "source_books": len(book_rows),
        "source_records": {
            "explicit": sum(len(records) for records in explicit_by_book.values()),
            "teaching": sum(len(records) for records in teaching_by_book.values()),
        },
        "source_occurrences": len(occurrence_rows),
        "canonical_concepts": len(concepts),
        "confusable_pairs": len(confusable_rows),
        "review_sheet_rows": len(review_sheet_rows),
        "review_sheet_priorities": dict(
            sorted(Counter(row["review_priority"] for row in review_sheet_rows).items())
        ),
        "manual_merge_groups": len(group_payload["groups"]),
        "auto_merged_groups": len(groups) - len(group_payload["groups"]),
        "review_status": "machine_reviewed",
        "review_method": "rule_assisted_machine_review_v2",
        "evidence_status": "ai_textbook_summary_unverified",
        "human_verified": False,
        "corrections": {
            "p0": len(p0_ids),
            "p1": len(p1_ids),
            "p2": len(p2_ids),
            "canonical_content_overrides": len(content_overrides),
        },
        "relations": {
            "resolved": sum(1 for row in relation_rows if row["resolution_status"] == "resolved"),
            "unresolved": sum(1 for row in relation_rows if row["resolution_status"] == "unresolved"),
            "ambiguous": sum(1 for row in relation_rows if row["resolution_status"] == "ambiguous"),
            "self_reference": sum(1 for row in relation_rows if row["resolution_status"] == "self_reference"),
            "external_prior": sum(1 for row in relation_rows if row["resolution_status"] == "external_prior"),
        },
        "relation_gaps": {
            "labels": len(relation_gap_rows),
            "relations": sum(row["relation_count"] for row in relation_gap_rows),
            "unresolved": sum(1 for row in relation_rows if row["resolution_status"] == "unresolved"),
            "ambiguous": sum(1 for row in relation_rows if row["resolution_status"] == "ambiguous"),
            "self_reference": sum(1 for row in relation_rows if row["resolution_status"] == "self_reference"),
            "external_prior": sum(1 for row in relation_rows if row["resolution_status"] == "external_prior"),
        },
        "ambiguous_aliases": len(ambiguous_aliases),
        "ambiguous_alias_labels": sorted(ambiguous_aliases),
        "quality": {
            "review_method": "rule_assisted_machine_review_v2",
            "concepts_with_open_issues": len(review_queue_rows),
            "blocking_concepts": blocking_concepts,
            "issue_codes": dict(sorted(issue_code_counts.items())),
            "concepts_with_unresolved_relations": sum(
                1
                for concept in concepts
                if any(
                    issue.startswith("unresolved relation:")
                    for issue in concept["quality"]["open_issues"]
                )
            ),
            "formula_validation": "not_performed",
            "equation_validation": "not_performed",
            "expert_review_required": True,
        },
    }

    if args.no_write:
        print(json.dumps(manifest_out, ensure_ascii=False, indent=2))
        print(f"relation unresolved counts: {dict(unresolved_counts)}")
        return

    CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
    (CANONICAL_DIR / "concepts.jsonl").write_text(
        format_jsonl(concepts), encoding="utf-8"
    )
    (CANONICAL_DIR / "occurrences.jsonl").write_text(
        format_jsonl(occurrence_rows), encoding="utf-8"
    )
    (CANONICAL_DIR / "relations.jsonl").write_text(
        format_jsonl(relation_rows), encoding="utf-8"
    )
    (CANONICAL_DIR / "review-queue.jsonl").write_text(
        format_jsonl(review_queue_rows), encoding="utf-8"
    )
    (CANONICAL_DIR / "relation-gaps.jsonl").write_text(
        format_jsonl(relation_gap_rows), encoding="utf-8"
    )
    (CANONICAL_DIR / "confusable-pairs.jsonl").write_text(
        format_jsonl(confusable_rows), encoding="utf-8"
    )
    (CANONICAL_DIR / "review-sheet.jsonl").write_text(
        format_jsonl(review_sheet_rows), encoding="utf-8"
    )
    (CANONICAL_DIR / "manifest.json").write_text(
        json.dumps(manifest_out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest_out, ensure_ascii=False, indent=2))
    print(f"Wrote canonical model to {CANONICAL_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
