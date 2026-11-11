from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


KINDS = ("resume", "cover_letter", "application_answers", "outreach")

_EXCERPT_LIMIT = 140
_EXCERPT_WINDOW = 100
_REQUIREMENT_LIMIT = 160
_MAX_NUMBER_FINDINGS = 8
_MAX_REGURGITATION_FINDINGS = 3
_MAX_JD_TERMS = 15
_MAX_MISSING_TERMS = 5
_MAX_MERGED_POSITIONS = 10
_SHARED_RUN_WORDS = 8
_MAX_GRAM_POSITIONS = 4
_MAX_RUN_UNIT_WORDS = 5000
_DEFAULT_LETTER_WORDS = (250, 420)
_SEVERITY_ORDER = {"error": 0, "warning": 1, "note": 2}
_MATERIAL_LABEL = {
    "resume": "resume",
    "cover_letter": "letter",
    "application_answers": "answer",
    "outreach": "message",
}
_COVERAGE_NOTE = "Add a missing term only where verified experience supports it."
_FORMAT_ALIASES = {
    "typ": "typ",
    "typst": "typ",
    "tex": "tex",
    "latex": "tex",
    "md": "md",
    "markdown": "md",
    "text": "text",
    "txt": "text",
    "plain": "text",
}

_WS_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,;])")
_ALNUM_RE = re.compile(r"[A-Za-z0-9]")
_KIND_SEPARATOR_RE = re.compile(r"[\s\-/]+")
_ESCAPED_PUNCT_RE = re.compile(r"\\([!-/:-@\[-`{-~])")
_PROTECTED_RE = re.compile("[\ue000-\ue0ff]")
_PROTECT_BASE = 0xE000

_TYP_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_TYP_LINE_COMMENT_RE = re.compile(r"(?<![:\\])//.*")
_TYP_DIRECTIVE_RE = re.compile(r"^#(?:import|include|let|show|set|if|for|while|context)\b")
_TYP_BRACKET_ONLY_RE = re.compile(r"^[\[\](){},;]+$")
_TYP_BULLET_RE = re.compile(r"^[-+]\s+(\S.*)$")
_TYP_HEADING_RE = re.compile(r"^=+\s+(.+)$")
_TYP_CALL_RE = re.compile(r"^#([A-Za-z_][\w.-]*)\s*([(\[])")
_TYP_IDENT_RE = re.compile(r"[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*")
_TYP_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_TYP_STRING_ARG_RE = re.compile(r'(?:([A-Za-z_][\w-]*)\s*:\s*)?"((?:[^"\\]|\\.)*)"')
_TYP_CONTENT_ARG_RE = re.compile(r"\[([^\[\]]+)\]")
_TYP_BOLD_RE = re.compile(r"\*(?=\S)([^*\n]+?)(?<=\S)\*")
_TYP_EMPH_RE = re.compile(r"(?<![A-Za-z0-9])_(?=\S)([^_\n]+?)(?<=\S)_(?![A-Za-z0-9])")
_TYP_LINEBREAK_RE = re.compile(r"\\(?=\s|$)")
_TYP_INVISIBLE_STRING_RE = re.compile(
    r"^(?:https?://|mailto:|tel:|www\.)"
    r"|^#[0-9a-fA-F]{3,8}$"
    r"|^-?[\d.]+(?:pt|em|cm|mm|in|fr|%)$"
    r"|\.(?:png|jpe?g|svg|gif|pdf|typ|bib|ya?ml|json|toml|csv)$",
    re.IGNORECASE,
)
_TYP_INLINE_FUNCS = frozenset(
    {
        "link",
        "text",
        "emph",
        "strong",
        "underline",
        "overline",
        "smallcaps",
        "highlight",
        "strike",
        "sub",
        "super",
        "box",
        "upper",
        "lower",
        "par",
    }
)
_TYP_SILENT_FUNCS = frozenset(
    {"image", "v", "h", "pagebreak", "colbreak", "line", "rect", "bibliography", "counter", "hide", "metadata"}
)
_TYP_SILENT_KEYS = frozenset(
    {"font", "lang", "region", "paper", "weight", "style", "fill", "stroke", "align", "numbering", "format"}
)

_TEX_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_TEX_ESCAPE_RE = re.compile(r"\\([&%$#_{}])")
_TEX_LINEBREAK_RE = re.compile(r"\\\\\*?(?:\[[^\]]*\])?")
_TEX_ITEM_RE = re.compile(r"\\item(?![A-Za-z])\s*(?:\[[^\]]*\])?")
_TEX_MACRO_ITEM_RE = re.compile(r"\\resumeItem\s*\{")
_TEX_ITEM_STOP_RE = re.compile(r"\\item(?![A-Za-z])|\\end\s*\{|\\resumeItem(?![A-Za-z])")
_TEX_HREF_RE = re.compile(r"\\href\s*\{[^{}]*\}\s*\{([^{}]*)\}")
_TEX_COLOR_ARG_RE = re.compile(r"\\(?:textcolor|colorbox)\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}")
_TEX_DROP_RE = re.compile(
    r"\\(?:vspace|hspace|begin|end|documentclass|usepackage|setlength|addtolength|input|include"
    r"|includegraphics|pagestyle|thispagestyle|pagenumbering|color|definecolor|fontsize|geometry"
    r"|newcommand|renewcommand|titleformat|titlespacing|label|ref|cite|hypersetup|linespread"
    r"|setlist|rule|fontfamily|selectfont|setmainfont|urlstyle|raisebox)\*?"
    r"(?:\s*(?:\[[^\]]*\]|\{[^{}]*\}))*"
)
_TEX_UNWRAP_RE = re.compile(r"\\(?!href\b)[A-Za-z@]+\*?\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
_TEX_BARE_COMMAND_RE = re.compile(r"\\[A-Za-z@]+\*?|\\[,;!:> /-]")
_TEX_LEFTOVER_RE = re.compile(r"[{}$]")
_TEX_SPACE_COLON_RE = re.compile(r"\s+:")
_TEX_LEADING_COMMAND_RE = re.compile(r"^\\([A-Za-z@]+)")
_TEX_TEXT_COMMANDS = frozenset(
    {
        "textbf",
        "textit",
        "emph",
        "href",
        "underline",
        "textsc",
        "texttt",
        "textsf",
        "textrm",
        "noindent",
        "indent",
        "small",
        "large",
        "Large",
        "normalsize",
        "footnotesize",
        "par",
    }
)

_MD_RULE_RE = re.compile(r"^(?:[-*_=]\s*){3,}$")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*$")
_MD_BULLET_RE = re.compile(r"^(?:[-*•–·◦▪‣]\s+|\d{1,2}[.)]\s+)(\S.*)$")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_CODE_RE = re.compile(r"`([^`]+)`")
_MD_STRONG_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_MD_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)

_LABEL_BULLET_RE = re.compile(r"^[A-Z][A-Za-z &/+-]{1,28}:\s")
_SECTION_WORD_RE = re.compile(r"[A-Za-z]+")
_SECTION_SKIP_WORDS = frozenset(
    {
        "skills",
        "skill",
        "technologies",
        "tools",
        "education",
        "certifications",
        "certification",
        "awards",
        "honors",
        "honours",
        "interests",
        "languages",
        "coursework",
        "publications",
        "references",
        "summary",
        "objective",
        "profile",
        "contact",
    }
)
_SECTION_EVIDENCE_WORDS = frozenset(
    {
        "experience",
        "employment",
        "projects",
        "project",
        "research",
        "leadership",
        "work",
        "volunteer",
        "volunteering",
        "activities",
        "history",
        "involvement",
        "internships",
    }
)
_SECTION_MODIFIER_WORDS = frozenset(
    {
        "technical",
        "core",
        "relevant",
        "selected",
        "professional",
        "additional",
        "key",
        "other",
        "academic",
        "and",
        "personal",
        "career",
        "extracurricular",
        "teaching",
        "open",
        "source",
        "industry",
    }
)
_SECTION_WORDS = _SECTION_SKIP_WORDS | _SECTION_EVIDENCE_WORDS | _SECTION_MODIFIER_WORDS

_SCAFFOLDING_RES = (
    re.compile(
        r"\[\s*(?:insert|your|company|hiring|recruiter|name|role|position|job|team|date|title|placeholder"
        r"|add|fill|specific|number|metric|x+|todo|tbd|employer|organization|product|contact|first|last"
        r"|full|recipient|manager|department|skill|school|university|address|city|industry)\b[^\]\n]{0,60}\]",
        re.IGNORECASE,
    ),
    re.compile(
        r"<\s*(?:company(?: name)?|employer|role|position|job title|title|(?:your )?name|hiring manager"
        r"|recruiter|team|date|insert[^>\n]{0,40}|placeholder)\s*>",
        re.IGNORECASE,
    ),
    re.compile(r"\{\{[^{}\n]{1,40}\}\}"),
    re.compile(r"\b(?:TODO|TBD|FIXME)\b"),
    re.compile(r"\blorem ipsum\b", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])(?:X{1,3}|N|Y)\s?%"),
    re.compile(r"\bX{2,}\b"),
    re.compile(
        r"\bas an AI(?:\s+(?:language\s+model|model|assistant|chatbot|system)\b|(?=\s*[,.;:])|\s*$)",
        re.IGNORECASE,
    ),
    re.compile(r"\bas a (?:large )?language model\b", re.IGNORECASE),
    re.compile(r"\bproof points?\b", re.IGNORECASE),
    re.compile(r"\btailoring requirements?\b", re.IGNORECASE),
    re.compile(r"\b(?:[Pp]er )?[Tt]he JD\b"),
    re.compile(r"\bATS[- ]friendly\b", re.IGNORECASE),
    re.compile(r"\bkeyword coverage\b", re.IGNORECASE),
)

_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_CLAIM_RE = re.compile(
    rf"""
    (?P<currency>[$€£]\s?(?P<currency_n>{_NUMBER})
        (?:\s?(?P<currency_m>[kKmMbB]|MM|[Bb]n|thousand|million|billion)(?![A-Za-z]))?\+?)
    |(?<![\w.,])(?:
        (?P<pct>(?P<pct_n>{_NUMBER})\s?(?:%|percent\b|pct\b))
        |(?P<mult>(?P<mult_n>{_NUMBER})(?:[x×](?![\w])|-?fold\b))
        |(?P<mag>(?P<mag_n>{_NUMBER})
            (?:(?P<mag_s>[kK]|MM|M|B|[Bb]n)(?![\w])|\s(?P<mag_w>thousand|million|billion|trillion)\b)\+?)
        |(?P<plus>(?P<plus_n>{_NUMBER})\+(?![\w+]))
        |(?P<plain>(?<![/:$€£-])(?P<plain_n>\d{{1,3}}(?:,\d{{3}})+|\d{{2,}})(?![\w.,]|[%/:×]|-\d))
    )
    """,
    re.VERBOSE,
)
_PHONE_RE = re.compile(r"(?<![\w.])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?!\w)")
_GPA_RE = re.compile(r"(?<![\w.])\d(?:\.\d+)?\s?/\s?\d(?:\.\d+)?(?![\w.])")
_FOLLOWING_WORDS_RE = re.compile(r"^(?:\s+|-)([A-Za-z][A-Za-z'’]*)(?:(?:\s+|-)([A-Za-z][A-Za-z'’]*))?")
_STREET_RE = re.compile(
    r"^\s+(?:[A-Z][A-Za-z.]*\s+){0,3}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way|Court|Ct|Suite|Ste)\b"
)
_SCREEN_WORD_RE = re.compile(r"^\s+(?:video|display|monitor|resolution|uhd|hdr|tv|footage)\b", re.IGNORECASE)
_SENTENCE_END_CHARS = ".!?:;"
_CORPUS_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_CORPUS_NUMBER_RE = re.compile(
    r"(?P<n>\d+(?:\.\d+)?)"
    r"(?:\s?(?P<pct>%|percent\b|pct\b|percentage\b)"
    r"|\s?(?P<mult>x\b|times\b|-?fold\b)"
    r"|\s?(?P<mag>k|m|mm|b|bn|thousand|million|billion|trillion)\b)?"
)
_MAGNITUDES = {
    "k": 1e3,
    "m": 1e6,
    "mm": 1e6,
    "b": 1e9,
    "bn": 1e9,
    "thousand": 1e3,
    "million": 1e6,
    "billion": 1e9,
    "trillion": 1e12,
}
_MONTHS = frozenset(
    "january february march april may june july august september october november december "
    "jan feb mar apr jun jul aug sep sept oct nov dec".split()
)
_NUMBER_STOPWORDS = frozenset(
    "a an and or to of in on at by for the with from as is was were are be been than then but that which "
    "when while where who it its this these those so if into per vs via not no".split()
)

_TECH_LEXICON = frozenset(
    "python java javascript typescript go golang rust ruby swift kotlin scala php perl sql bash matlab julia "
    "react angular vue svelte django flask fastapi rails spring express node docker kubernetes terraform "
    "ansible jenkins git github gitlab linux aws gcp azure postgres postgresql mysql sqlite mongodb redis "
    "kafka spark hadoop airflow dbt snowflake bigquery databricks pandas numpy pytorch tensorflow keras "
    "scikit-learn tableau excel figma jira graphql grpc rest html css sass webpack redux celery rabbitmq "
    "elasticsearch nginx lambda dynamodb s3 ec2 langchain openai llamaindex pgvector selenium pytest junit "
    "windows macos ios android oracle salesforce".split()
)
_JD_SKILL_LEXICON = _TECH_LEXICON | frozenset(
    "ajax jquery bootstrap tailwind nextjs nuxt remix vite babel jest cypress playwright mocha rspec "
    "c c++ c# objective-c r dart elixir erlang haskell clojure lua groovy vba powershell shell "
    "dotnet asp.net blazor laravel symfony hibernate maven gradle npm yarn pnpm pip conda poetry "
    "kubernetes helm istio prometheus grafana datadog splunk sentry kibana logstash opentelemetry "
    "cloudformation pulumi circleci travis bitbucket svn perforce "
    "redshift athena glue emr kinesis sqs sns ecs eks fargate rds aurora cloudwatch iam vpc "
    "pubsub dataflow dataproc vertex firebase firestore supabase vercel netlify heroku cloudflare "
    "cassandra couchbase neo4j clickhouse duckdb presto trino hive hbase flink beam nifi informatica "
    "talend fivetran looker powerbi qlik sas spss stata alteryx "
    "llm llms rag embeddings transformers huggingface langgraph mcp agents agentic bert gpt "
    "opencv nltk spacy xgboost lightgbm mlflow kubeflow sagemaker onnx cuda "
    "microservices serverless websockets oauth saml sso jwt openapi swagger soap protobuf "
    "etl elt olap oltp cdc ci cd devops mlops sre tdd bdd agile scrum kanban "
    "unix ubuntu redhat centos vmware nutanix citrix sccm intune okta servicenow zendesk "
    "sap workday netsuite hubspot marketo qualtrics sharepoint confluence notion asana airtable "
    "photoshop illustrator sketch invision webflow wordpress shopify "
    "embedded rtos fpga verilog vhdl plc scada autocad solidworks simulink labview "
    "hipaa gdpr soc2 pci fedramp nist iso".split()
)
_JD_NON_SKILL_ACRONYMS = frozenset(
    "usa us uk eu eoe eeo pto llc inc ltd hr ceo cto cfo coo vp svp evp phd mba bs ba ms ma bsc msc gpa "
    "am pm est pst cst mst utc ny nj ca tx wa ma il fl co ga nc va pa oh mi az or dc nyc sf la "
    "id ok etc ie eg faq tbd na dei erg adp lgbtq lgbt ada fmla ssn dob hq yoe ote rsu rsus k".split()
)
_STACK_TRIGGER_RE = re.compile(r"\b(using|with|via|leveraging|utilizing|in)\s+", re.IGNORECASE)
_STACK_STRICT_TRIGGERS = frozenset({"with", "in"})
_STACK_SPLIT_RE = re.compile(r"\s*[,;]\s*(?:and\s+|&\s+)?|\s+(?:and|&)\s+")
_UNIT_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?-?[a-z]+$")
_TOKEN_STRIP_CHARS = "()[]\"'“”‘’,;:!?"
_NON_TECH_TOKENS = frozenset(
    "e.g i.e etc vs us usa eu uk apac emea latam ceo cto cfo coo vp hr kpi kpis okr okrs roi b2b b2c "
    "q1 q2 q3 q4 h1 h2".split()
)

_AI_TELLS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("delve", re.compile(r"\bdelv(?:e|es|ed|ing)\b", re.IGNORECASE)),
    ("tapestry", re.compile(r"\btapestry\b", re.IGNORECASE)),
    ("testament to", re.compile(r"\btestament to\b", re.IGNORECASE)),
    ("in today's fast-paced", re.compile(r"\bin today['’]s fast[- ]paced\b", re.IGNORECASE)),
    ("ever-evolving", re.compile(r"\bever[- ]evolving\b", re.IGNORECASE)),
    (
        "navigate the complexities",
        re.compile(r"\bnavigat(?:e|es|ed|ing) the complexit(?:y|ies)\b", re.IGNORECASE),
    ),
    ("at the intersection of", re.compile(r"\bat the intersection of\b", re.IGNORECASE)),
    ("it's worth noting", re.compile(r"\bit(?:['’]s| is) worth noting\b", re.IGNORECASE)),
    ("not only … but also", re.compile(r"\bnot only\b[^.!?]{1,120}?\bbut also\b", re.IGNORECASE)),
    ("seamlessly", re.compile(r"\bseamlessly\b", re.IGNORECASE)),
    ("leverage", re.compile(r"\bleverag(?:e|es|ed|ing)\b", re.IGNORECASE)),
    ("utilize", re.compile(r"\butiliz(?:e|es|ed|ing)\b", re.IGNORECASE)),
    ("spearheaded", re.compile(r"\bspearheaded\b", re.IGNORECASE)),
    ("synergy", re.compile(r"\bsynerg\w*", re.IGNORECASE)),
    ("cutting-edge", re.compile(r"\bcutting[- ]edge\b", re.IGNORECASE)),
    ("state-of-the-art", re.compile(r"\bstate[- ]of[- ]the[- ]art\b", re.IGNORECASE)),
    ("robust", re.compile(r"\brobust\b", re.IGNORECASE)),
)
_LEVERAGE_NOUN_LEADS = frozenset(
    "the a of more much less financial operating operational negotiating greater significant high low its "
    "their our my his her your no any some this that strategic competitive political economic additional "
    "with for in on as gain gained gaining provide provides provided providing create created creating".split()
)
_LEVERAGE_NOUN_TAILS = frozenset("buyout buyouts finance loan loans lending etf etfs fund funds".split())
_LAST_WORD_RE = re.compile(r"([A-Za-z'’-]+)\W*$")
_FIRST_WORD_RE = re.compile(r"^\W*([A-Za-z'’-]+)")

_WEAK_OPENER_RE = re.compile(
    r"^\W*(?:responsible for|worked on|helped(?: to)?|assisted(?: with| in)?|participated in|involved in"
    r"|tasked with|duties included?|in charge of|contributed to|exposure to|familiar with|gained experience)\b",
    re.IGNORECASE,
)
_GENERIC_QUALITIES = r"(?:efficiency|performance|productivity|reliability|scalability|user experience)"
_MANUFACTURED_ENDING_RE = re.compile(
    r"\b(?:"
    rf"improv(?:e|es|ed|ing) (?:overall )?{_GENERIC_QUALITIES}"
    rf"|enhanc(?:e|es|ed|ing) (?:overall )?{_GENERIC_QUALITIES}"
    r"|increas(?:e|es|ed|ing) (?:overall )?(?:efficiency|productivity)"
    r"|streamlin(?:e|es|ed|ing) (?:processes|operations|workflows)"
    r"|optimiz(?:e|es|ed|ing) performance"
    r"|ensur(?:e|es|ed|ing) (?:scalability|reliability|quality)"
    r"|driving (?:business )?(?:value|impact|results)"
    r")\b",
    re.IGNORECASE,
)
_CONSEQUENCE_RE = re.compile(
    r"\bso\b(?! (?:far|much|many|called)\b)|\benabling\b|\benabled\b|\ballowing\b|\ballowed\b|\bletting\b"
    r"|\bwhich (?:cut|reduced|let|enabled|prevented|removed|made)\b|\breduc\w*|\bcut(?:s|ting)?\b"
    r"|\beliminat\w*|\bprevent\w*|\bsav(?:ed|ing)\b|\bshortened\b|\bunblocked\b|\breplac\w*|\bshipped\b"
    r"|\blaunched\b|\bdeployed\b|\breleased\b|\badopted\b|\bused by\b|\bpresented\b|\bpublished\b"
    r"|\baccepted\b|\bwon\b|\bawarded\b|\bselected\b|\bfrom\b.+\bto\b|\binstead of\b|\bwithout\b"
    r"|\bresult(?:ed|ing) in\b|\bled to\b",
    re.IGNORECASE,
)
_DIGIT_RE = re.compile(r"\d")
_FIRST_PERSON_I_RE = re.compile(r"(?<![\w'’@./-])I(['’](?:m|ve|d|ll))?(?![\w'’@/-]|\.\w)")
_FIRST_PERSON_OTHER_RE = re.compile(
    r"(?<![\w'’@./-])(?:[Mm]y|me|[Ww]e(?:['’](?:re|ve|ll|d))?|[Oo]ur)(?![\w'’@/-]|\.\w)"
)
_DOUBLE_HYPHEN_RE = re.compile(r"-{2,}")
_PAST_IRREGULAR = frozenset(
    "built led wrote ran drove made won grew taught sold brought took began held kept oversaw rebuilt "
    "spoke gave found chose met sent spent rewrote sought".split()
)
_NOT_PAST = frozenset({"embed", "exceed", "proceed", "succeed", "speed", "feed", "need", "seed"})
_NOT_GERUND = frozenset(
    {"during", "engineering", "marketing", "bring", "string", "spring", "nothing", "everything", "something"}
)
_PRESENT_VERB_BASES = frozenset(
    "build lead manage develop design maintain own run write create implement drive support work "
    "collaborate coordinate analyze automate deploy deliver mentor train test review research monitor "
    "optimize architect engineer partner oversee ship launch improve reduce define plan conduct handle "
    "serve teach integrate migrate operate produce present track evaluate configure debug document "
    "facilitate guide investigate prototype scale refactor provide perform prepare organize supervise "
    "translate advise assist help use contribute generate".split()
)

_GENERIC_ENTHUSIASM_RES = (
    re.compile(
        r"\bI(?: am|['’]m) (?:very |truly |so |extremely |really )?(?:excited|thrilled|delighted|eager)"
        r" to (?:apply|submit)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bI am writing to (?:express|apply)\b", re.IGNORECASE),
    re.compile(r"\bpassionate about\b", re.IGNORECASE),
    re.compile(r"\bdream (?:job|company|role)\b", re.IGNORECASE),
    re.compile(r"\bperfect (?:fit|match|candidate)\b", re.IGNORECASE),
    re.compile(r"\b(?:great|ideal|strong) fit for\b", re.IGNORECASE),
    re.compile(r"\besteemed (?:company|organization)\b", re.IGNORECASE),
    re.compile(r"\bfast-paced environment\b", re.IGNORECASE),
    re.compile(r"\bI believe I would be\b", re.IGNORECASE),
    re.compile(r"\bhit the ground running\b", re.IGNORECASE),
    re.compile(r"\bthink(?:ing)? outside the box\b", re.IGNORECASE),
    re.compile(r"\bteam player\b", re.IGNORECASE),
    re.compile(r"\bwear(?:ing)? many hats\b", re.IGNORECASE),
)
_COMPANY_SUFFIXES = frozenset(
    "inc incorporated llc corp corporation ltd limited co company gmbh plc lp llp".split()
)
_COMPANY_WORD_RE = re.compile(r"[a-z0-9]+")
_RUN_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")
_SALUTATION_RE = re.compile(
    r"^(?:(?:dear|hello|hi|hey|greetings|good (?:morning|afternoon))\b[^!?\n]{0,60}?[,:]"
    r"|to whom it may concern[,:]?)\s*",
    re.IGNORECASE,
)
_RECITAL_RE = re.compile(
    r"^(?:my name is\b|I(?: am|['’]m) an? (?:[\w'’-]+ ){0,6}?(?:student|graduate|engineer|developer|professional)\b)",
    re.IGNORECASE,
)
_STOCK_OPENER_RES = (
    re.compile(r"\bI hope this (?:message|email|note) finds you well\b", re.IGNORECASE),
    re.compile(r"\bI hope you(?:['’]re| are) doing well\b", re.IGNORECASE),
    re.compile(r"\bmy name is\b", re.IGNORECASE),
    re.compile(r"\bI came across your profile\b", re.IGNORECASE),
    re.compile(r"\bI wanted to reach out\b", re.IGNORECASE),
    re.compile(r"\bsorry to bother you\b", re.IGNORECASE),
)
_CLEAR_ASK_RE = re.compile(
    r"\?|\bwould you be open\b|\bcould you\b|\bcan you\b|\bwould it be possible\b|\bhappy to\b|\blet me know\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_OUTREACH_NOTE_WORDS = 110
_OUTREACH_MAX_WORDS = 150

_TERM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.]*")
_TECH_CHARS_RE = re.compile(r"[\d+#.]")
_JD_SENTENCE_PUNCT_RE = re.compile(r"[.,;]")
_JD_SENTENCE_START_CHARS = ".!?:•*–—-"
_JD_STATE_CODE_RE = re.compile(r"(?<=[a-z]),\s*[A-Z]{2}(?=\s*(?:$|[()|•·-]|\d{5}))", re.MULTILINE)
_STOPWORDS = frozenset(
    "a about above across after again against all also am an and any are as at be because been before "
    "being below between both but by can could did do does doing done down during each either else few "
    "for from further had has have having he her here hers him his how however i if in into is it its "
    "just ll may me might more most much my new no nor not now of off on once one only or other our "
    "ours out over own per re same she should so some such than that the their theirs them then there "
    "these they this those through to too two under until up upon us ve very was we well were what "
    "when where whether which while who whom why will with within without would you your yours "
    "e.g i.e etc "
    "experience experienced ability able strong excellent work working team teams including include "
    "includes required require requires preferred plus years year skills skill knowledge understanding "
    "familiarity familiar proficiency proficient role roles candidate candidates responsibilities "
    "responsibility requirements requirement qualifications qualification must using use used build "
    "building develop developing looking seeking join ideal minimum least equivalent related relevant "
    "demonstrated proven track record good great solid deep hands like want need needs help across "
    "ensure make world day days month months time full part position job company opportunity "
    "opportunities equal employer bachelor bachelors master masters degree phd english remote hybrid "
    "usa san francisco york united states benefits salary compensation apply applicants engineer "
    "engineers engineering computer senior junior".split()
)


@dataclass(frozen=True)
class _Unit:
    kind: str
    text: str
    line: int
    index: int = 0
    evidence: bool = True


@dataclass(frozen=True)
class _Finding:
    rule: str
    severity: str
    where: str
    excerpt: str
    fix: str
    line: int = 0


@dataclass(frozen=True)
class _Claim:
    cls: str
    value: float
    start: int
    surface: str


@dataclass(frozen=True)
class _Context:
    kind: str
    fmt: str
    source: str
    units: tuple[_Unit, ...]
    bullets: tuple[_Unit, ...]
    paragraphs: tuple[_Unit, ...]
    body: tuple[_Unit, ...]
    evidence_bullets: tuple[_Unit, ...]
    plain: str
    body_words: int
    requirements: tuple[str, ...]
    job_description: str
    evidence_corpus: str
    company: str
    names: frozenset[str]
    company_words: frozenset[str]
    max_chars: int | None
    writing: dict[str, Any]


@dataclass(frozen=True)
class _Rule:
    id: str
    severity: str
    kinds: tuple[str, ...]
    check: Callable[[_Context], list[_Finding]]


def normalize_kind(value: str | None) -> str:
    key = _KIND_SEPARATOR_RE.sub("_", str(value or "").strip().lower().replace("é", "e")).strip("_")
    if key in KINDS:
        return key
    if key in {"cv", "curriculum_vitae"} or key.startswith("resume"):
        return "resume"
    if "cover" in key or "letter" in key:
        return "cover_letter"
    if any(marker in key for marker in ("answer", "essay", "question")):
        return "application_answers"
    if any(marker in key for marker in ("outreach", "email", "linkedin", "message", "network", "referral")):
        return "outreach"
    raise ValueError(f"Unknown material kind {value!r}; expected one of: {', '.join(KINDS)}")


def extract_material_text(source: str, fmt: str = "text") -> dict:
    units = _extract_units(source, _normalize_fmt(fmt))
    return {
        "bullets": [{"text": unit.text, "line": unit.line} for unit in units if unit.kind == "bullet"],
        "paragraphs": [{"text": unit.text, "line": unit.line} for unit in units if unit.kind == "paragraph"],
        "plain": "\n".join(unit.text for unit in units),
    }


def rules_for(kind: str) -> tuple[str, ...]:
    resolved = normalize_kind(kind)
    return tuple(rule.id for rule in _RULES if resolved in rule.kinds)


def check_material(
    source: str,
    *,
    kind: str,
    fmt: str = "text",
    requirements: list[str] | None = None,
    job_description: str = "",
    evidence_corpus: str = "",
    company: str = "",
    candidate_name: str = "",
    max_chars: int | None = None,
    config: dict | None = None,
    max_findings: int = 40,
) -> dict:
    resolved = normalize_kind(kind)
    resolved_fmt = _normalize_fmt(fmt)
    text = str(source or "")
    units = tuple(_extract_units(text, resolved_fmt))
    bullets = tuple(unit for unit in units if unit.kind == "bullet")
    paragraphs = tuple(unit for unit in units if unit.kind == "paragraph")
    body = tuple(unit for unit in units if unit.kind != "heading")
    plain = "\n".join(unit.text for unit in units)
    writing = config.get("writing") if isinstance(config, dict) else None
    if isinstance(requirements, str):
        requirements = [requirements]
    context = _Context(
        kind=resolved,
        fmt=resolved_fmt,
        source=text,
        units=units,
        bullets=bullets,
        paragraphs=paragraphs,
        body=body,
        evidence_bullets=tuple(unit for unit in bullets if unit.evidence),
        plain=plain,
        body_words=sum(_count_words(unit.text) for unit in body),
        requirements=tuple(str(item).strip() for item in (requirements or []) if str(item or "").strip()),
        job_description=str(job_description or ""),
        evidence_corpus=str(evidence_corpus or ""),
        company=str(company or ""),
        names=frozenset(_COMPANY_WORD_RE.findall(f"{company or ''} {candidate_name or ''}".lower())),
        company_words=frozenset(_COMPANY_WORD_RE.findall(str(company or "").lower())),
        max_chars=max_chars,
        writing=writing if isinstance(writing, dict) else {},
    )

    ranked: list[tuple[int, int, int, int, _Finding]] = []
    for rule_order, rule in enumerate(_RULES):
        if resolved not in rule.kinds:
            continue
        for sequence, finding in enumerate(rule.check(context)):
            ranked.append((_SEVERITY_ORDER[finding.severity], finding.line, rule_order, sequence, finding))
    ranked.sort(key=lambda item: item[:4])
    findings = [item[4] for item in ranked]

    counts = {severity: 0 for severity in _SEVERITY_ORDER}
    for finding in findings:
        counts[finding.severity] += 1
    limit = len(findings) if max_findings is None else max(0, int(max_findings))
    result: dict[str, Any] = {
        "kind": resolved,
        "status": "review" if counts["error"] or counts["warning"] else "pass",
        "summary": {
            "words": _count_words(plain),
            "bullets": len(bullets),
            "paragraphs": len(paragraphs),
            "errors": counts["error"],
            "warnings": counts["warning"],
            "notes": counts["note"],
        },
        "findings": [
            {
                "rule": finding.rule,
                "severity": finding.severity,
                "where": finding.where,
                "excerpt": finding.excerpt,
                "fix": finding.fix,
            }
            for finding in findings[:limit]
        ],
    }
    if len(findings) > limit:
        result["findings_truncated"] = len(findings) - limit
    coverage = _coverage(context)
    if coverage is not None:
        result["coverage"] = coverage
    return result


def _normalize_fmt(fmt: str | None) -> str:
    return _FORMAT_ALIASES.get(str(fmt or "").strip().lower().lstrip("."), "text")


def _squash(text: str) -> str:
    return _SPACE_BEFORE_PUNCT_RE.sub(r"\1", _WS_RE.sub(" ", text)).strip()


def _count_words(text: str) -> int:
    return sum(1 for token in text.split() if _ALNUM_RE.search(token))


def _clip(text: str, limit: int = _EXCERPT_LIMIT) -> str:
    text = _WS_RE.sub(" ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _excerpt(text: str, start: int, end: int) -> str:
    if len(text) <= _EXCERPT_WINDOW:
        return text
    begin = text.rfind(" ", 0, max(0, start - 30)) + 1
    stop = text.find(" ", min(len(text), end + 40))
    if stop < 0:
        stop = len(text)
    return _clip(("…" if begin else "") + text[begin:stop] + ("…" if stop < len(text) else ""))


def _protect(match: re.Match[str]) -> str:
    # Escaped punctuation is parked in the private-use area so markup stripping cannot touch it.
    return chr(_PROTECT_BASE + ord(match.group(1)))


def _restore(text: str) -> str:
    return _PROTECTED_RE.sub(lambda match: chr(ord(match.group(0)) - _PROTECT_BASE), text)


class _Collector:
    def __init__(self, clean: Callable[[str], str]) -> None:
        self._clean = clean
        self.items: list[tuple[str, str, int]] = []
        self._paragraph: list[str] = []
        self._paragraph_line = 0
        self._bullet: list[str] = []
        self._bullet_line = 0
        self._bullet_indent = -1

    def flush(self) -> None:
        if self._bullet:
            self._emit("bullet", " ".join(self._bullet), self._bullet_line)
            self._bullet = []
            self._bullet_indent = -1
        if self._paragraph:
            self._emit("paragraph", " ".join(self._paragraph), self._paragraph_line)
            self._paragraph = []

    def start_bullet(self, text: str, line: int, indent: int) -> None:
        self.flush()
        self._bullet = [text]
        self._bullet_line = line
        self._bullet_indent = indent

    def add_line(self, text: str, line: int, indent: int) -> None:
        if self._bullet and indent > self._bullet_indent:
            self._bullet.append(text)
            return
        if self._bullet:
            self.flush()
        if not self._paragraph:
            self._paragraph_line = line
        self._paragraph.append(text)

    def heading(self, text: str, line: int, *, cleaned: bool = False) -> None:
        self.flush()
        self._emit("heading", text, line, cleaned=cleaned)

    def _emit(self, kind: str, text: str, line: int, *, cleaned: bool = False) -> None:
        value = _squash(text) if cleaned else self._clean(text)
        if _ALNUM_RE.search(value):
            self.items.append((kind, value, line))


def _extract_units(source: str, fmt: str) -> list[_Unit]:
    text = str(source or "").replace("\r\n", "\n").replace("\r", "\n")
    if fmt == "typ":
        raw = _extract_typst(text)
    elif fmt == "tex":
        raw = _extract_tex(text)
    else:
        raw = _extract_marked(text)
    return _finalize_units(raw)


def _finalize_units(raw: list[tuple[str, str, int]]) -> list[_Unit]:
    units: list[_Unit] = []
    section = ""
    bullet_index = 0
    paragraph_index = 0
    for kind, text, line in raw:
        state = _section_state(text) if kind != "bullet" else ""
        if kind == "paragraph" and state:
            kind = "heading"
        if kind == "heading":
            section = state or section
            units.append(_Unit("heading", text, line))
        elif kind == "bullet":
            bullet_index += 1
            evidence = section != "skip" and not _LABEL_BULLET_RE.match(text)
            units.append(_Unit("bullet", text, line, bullet_index, evidence))
        else:
            paragraph_index += 1
            units.append(_Unit("paragraph", text, line, paragraph_index))
    return units


def _section_state(text: str) -> str:
    words = [word.lower() for word in _SECTION_WORD_RE.findall(text)]
    if not words or len(words) > 5 or len(text) > 60 or any(word not in _SECTION_WORDS for word in words):
        return ""
    if any(word in _SECTION_SKIP_WORDS for word in words):
        return "skip"
    if any(word in _SECTION_EVIDENCE_WORDS for word in words):
        return "evidence"
    return ""


def _bracket_delta(line: str, opens: str, closes: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    for char in line:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in opens:
            depth += 1
        elif char in closes:
            depth -= 1
    return depth


def _match_bracket(text: str, start: int, open_char: str, close_char: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    string_aware = open_char == "("
    for position in range(start, len(text)):
        char = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif string_aware and char == '"':
            in_string = True
        elif char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return position
    return -1


def _typst_unwrap(text: str) -> str:
    out: list[str] = []
    position = 0
    length = len(text)
    while position < length:
        char = text[position]
        match = _TYP_IDENT_RE.match(text, position + 1) if char == "#" else None
        if match is None:
            out.append(char)
            position += 1
            continue
        cursor = match.end()
        first_string = ""
        if cursor < length and text[cursor] == "(":
            end = _match_bracket(text, cursor, "(", ")")
            if end < 0:
                out.append(" ")
                break
            string_match = _TYP_STRING_RE.search(text, cursor, end)
            first_string = string_match.group(1) if string_match else ""
            cursor = end + 1
        blocks: list[str] = []
        while cursor < length and text[cursor] == "[":
            end = _match_bracket(text, cursor, "[", "]")
            if end < 0:
                blocks.append(text[cursor + 1 :])
                cursor = length
                break
            blocks.append(text[cursor + 1 : end])
            cursor = end + 1
        if blocks:
            out.append(" ".join(_typst_unwrap(block) for block in blocks))
        elif match.group(0) == "link" and first_string:
            out.append(first_string)
        else:
            out.append(" ")
        position = cursor
    return "".join(out)


def _typst_inline(text: str) -> str:
    text = _ESCAPED_PUNCT_RE.sub(_protect, text)
    text = _typst_unwrap(text)
    text = _TYP_BOLD_RE.sub(r"\1", text)
    text = _TYP_EMPH_RE.sub(r"\1", text)
    text = _TYP_LINEBREAK_RE.sub(" ", text.replace("~", " "))
    text = text.strip()
    while text.endswith("]") and text.count("]") > text.count("["):
        text = text[:-1].rstrip()
    while text.startswith("[") and text.count("[") > text.count("]"):
        text = text[1:].lstrip()
    return _squash(_restore(text))


def _typst_arg_texts(args: str) -> list[str]:
    texts: list[str] = []
    for match in _TYP_STRING_ARG_RE.finditer(args):
        value = match.group(2).replace('\\"', '"').strip()
        if (match.group(1) or "").lower() in _TYP_SILENT_KEYS or _TYP_INVISIBLE_STRING_RE.search(value):
            continue
        texts.append(value)
    remainder = _TYP_STRING_ARG_RE.sub(" ", args)
    texts.extend(_typst_inline(match.group(1)) for match in _TYP_CONTENT_ARG_RE.finditer(remainder))
    return [text for text in texts if _ALNUM_RE.search(text)]


def _typst_call_texts(line: str, match: re.Match[str]) -> list[str]:
    if match.group(1) in _TYP_SILENT_FUNCS:
        return []
    texts: list[str] = []
    if match.group(2) == "(":
        start = match.end() - 1
        end = _match_bracket(line, start, "(", ")")
        texts.extend(_typst_arg_texts(line[start + 1 : end if end >= 0 else len(line)]))
    trailing = _typst_inline(line)
    if _ALNUM_RE.search(trailing):
        texts.append(trailing)
    return texts


def _extract_typst(source: str) -> list[tuple[str, str, int]]:
    text = _TYP_BLOCK_COMMENT_RE.sub(lambda match: "\n" * match.group(0).count("\n"), source)
    collector = _Collector(_typst_inline)
    skip_depth = 0
    call_depth = 0
    for number, raw_line in enumerate(text.split("\n"), 1):
        line = _TYP_LINE_COMMENT_RE.sub("", raw_line).rstrip()
        stripped = line.strip()
        if skip_depth > 0:
            skip_depth = max(0, skip_depth + _bracket_delta(stripped, "([{", ")]}"))
            continue
        if _TYP_DIRECTIVE_RE.match(stripped):
            collector.flush()
            skip_depth = max(0, _bracket_delta(stripped, "([{", ")]}"))
            continue
        if call_depth > 0:
            call_depth = max(0, call_depth + _bracket_delta(stripped, "(", ")"))
            in_call = True
        else:
            in_call = False
        if not stripped or _TYP_BRACKET_ONLY_RE.match(stripped):
            collector.flush()
            continue
        indent = len(line) - len(line.lstrip())
        bullet = _TYP_BULLET_RE.match(stripped)
        if bullet:
            collector.start_bullet(bullet.group(1), number, indent)
            continue
        if in_call:
            for value in _typst_arg_texts(stripped):
                collector.heading(value, number, cleaned=True)
            continue
        heading = _TYP_HEADING_RE.match(stripped)
        if heading:
            collector.heading(heading.group(1), number)
            continue
        call = _TYP_CALL_RE.match(stripped)
        if call and call.group(1) not in _TYP_INLINE_FUNCS:
            for value in _typst_call_texts(stripped, call):
                collector.heading(value, number, cleaned=True)
            collector.flush()
            call_depth = max(0, _bracket_delta(stripped, "(", ")"))
            continue
        collector.add_line(stripped, number, indent)
    collector.flush()
    return collector.items


def _tex_inline(text: str) -> str:
    text = _TEX_ESCAPE_RE.sub(_protect, text)
    text = _TEX_LINEBREAK_RE.sub(" ", text).replace("~", " ").replace("}{", "} {")
    previous = None
    while previous != text:
        previous = text
        text = _TEX_HREF_RE.sub(r"\1", text)
        text = _TEX_COLOR_ARG_RE.sub("", text)
        text = _TEX_DROP_RE.sub(" ", text)
        text = _TEX_UNWRAP_RE.sub(r"\1", text)
    text = _TEX_BARE_COMMAND_RE.sub(" ", text)
    text = _TEX_LEFTOVER_RE.sub("", text)
    text = text.replace("``", '"').replace("''", '"')
    return _TEX_SPACE_COLON_RE.sub(":", _squash(_restore(text)))


def _extract_tex(source: str) -> list[tuple[str, str, int]]:
    text = "\n".join(_TEX_COMMENT_RE.sub("", line) for line in source.split("\n"))
    start = 0
    end = len(text)
    begin_marker = "\\begin{document}"
    begin = text.find(begin_marker)
    if begin >= 0:
        start = begin + len(begin_marker)
    finish = text.find("\\end{document}", start)
    if finish >= 0:
        end = finish
    body = text[start:end]
    base_line = text.count("\n", 0, start) + 1

    items: list[tuple[int, int, str, str, int]] = []
    masked = list(body)

    def record_bullet(span_start: int, text_start: int, text_end: int, span_end: int) -> None:
        cleaned = _tex_inline(body[text_start:text_end])
        if _ALNUM_RE.search(cleaned):
            line = base_line + body.count("\n", 0, span_start)
            items.append((line, len(items), "bullet", cleaned, line))
        for position in range(span_start, span_end):
            if masked[position] != "\n":
                masked[position] = " "

    for match in _TEX_ITEM_RE.finditer(body):
        stop = _TEX_ITEM_STOP_RE.search(body, match.end())
        text_end = stop.start() if stop else len(body)
        record_bullet(match.start(), match.end(), text_end, text_end)
    for match in _TEX_MACRO_ITEM_RE.finditer(body):
        close = _match_bracket(body, match.end() - 1, "{", "}")
        text_end = close if close >= 0 else len(body)
        record_bullet(match.start(), match.end(), text_end, min(len(body), text_end + 1))

    collector = _Collector(_squash)
    for offset, raw_line in enumerate("".join(masked).split("\n")):
        stripped = raw_line.strip()
        cleaned = _tex_inline(stripped) if stripped else ""
        if not _ALNUM_RE.search(cleaned):
            collector.flush()
            continue
        command = _TEX_LEADING_COMMAND_RE.match(stripped)
        if command and command.group(1) not in _TEX_TEXT_COMMANDS:
            collector.heading(cleaned, base_line + offset, cleaned=True)
            continue
        collector.add_line(cleaned, base_line + offset, 0)
    collector.flush()
    for kind, value, line in collector.items:
        items.append((line, len(items), kind, value, line))
    items.sort(key=lambda item: item[:2])
    return [(kind, value, line) for _, _, kind, value, line in items]


def _marked_inline(text: str) -> str:
    text = _ESCAPED_PUNCT_RE.sub(_protect, text)
    text = _MD_BREAK_RE.sub(" ", text)
    text = _MD_IMAGE_RE.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_CODE_RE.sub(r"\1", text)
    text = _MD_STRONG_RE.sub(lambda match: match.group(1) or match.group(2), text)
    text = _TYP_BOLD_RE.sub(r"\1", text)
    text = _TYP_EMPH_RE.sub(r"\1", text)
    return _squash(_restore(text))


def _extract_marked(source: str) -> list[tuple[str, str, int]]:
    collector = _Collector(_marked_inline)
    for number, raw_line in enumerate(source.split("\n"), 1):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or _MD_RULE_RE.match(stripped):
            collector.flush()
            continue
        indent = len(line) - len(line.lstrip())
        heading = _MD_HEADING_RE.match(stripped)
        if heading:
            collector.heading(heading.group(1), number)
            continue
        bullet = _MD_BULLET_RE.match(stripped)
        if bullet:
            collector.start_bullet(bullet.group(1), number, indent)
            continue
        collector.add_line(stripped, number, indent)
    collector.flush()
    return collector.items


def _where(unit: _Unit) -> str:
    if unit.kind == "heading":
        return f"line {unit.line}"
    return f"{unit.kind} {unit.index} (line {unit.line})"


def _merged_where(units: list[_Unit]) -> str:
    if len(units) == 1:
        return _where(units[0])
    parts: list[str] = []
    for kind, label in (("bullet", "bullets"), ("paragraph", "paragraphs"), ("heading", "lines")):
        numbers = [unit.line if kind == "heading" else unit.index for unit in units if unit.kind == kind]
        if not numbers:
            continue
        if len(numbers) == 1:
            label = "line" if kind == "heading" else kind
        shown = ", ".join(str(number) for number in numbers[:_MAX_MERGED_POSITIONS])
        extra = len(numbers) - _MAX_MERGED_POSITIONS
        parts.append(f"{label} {shown}" + (f" +{extra} more" if extra > 0 else ""))
    return "; ".join(parts)


def _finding(
    rule: str,
    unit: _Unit | None,
    excerpt: str,
    fix: str,
    *,
    severity: str = "",
    where: str = "",
    kind: str = "",
) -> _Finding:
    return _Finding(
        rule=rule,
        severity=severity or _SEVERITIES[rule],
        where=where or (_where(unit) if unit else _MATERIAL_LABEL.get(kind, "material")),
        excerpt=_clip(excerpt),
        fix=fix,
        line=unit.line if unit else 0,
    )


def _check_scaffolding_leak(context: _Context) -> list[_Finding]:
    findings: list[_Finding] = []
    for unit in context.units:
        spans: list[tuple[int, int]] = []
        for pattern in _SCAFFOLDING_RES:
            match = pattern.search(unit.text)
            if not match or any(match.start() < end and start < match.end() for start, end in spans):
                continue
            spans.append(match.span())
            findings.append(
                _finding(
                    "scaffolding_leak",
                    unit,
                    _excerpt(unit.text, match.start(), match.end()),
                    f'Remove the internal or placeholder text "{_clip(match.group(0), 40)}" and write the real, '
                    "verified content.",
                )
            )
    return findings


def _to_number(raw: str, magnitude: str | None = None) -> float:
    return round(float(raw.replace(",", "")) * _MAGNITUDES.get((magnitude or "").lower(), 1.0), 6)


def _blank(match: re.Match[str]) -> str:
    return " " * len(match.group(0))


def _counts_something(text: str, match: re.Match[str]) -> bool:
    # A bare integer is a claim only when it quantifies a following noun and is not a version, date or address.
    before = text[: match.start()]
    if before.endswith(" "):
        tokens = before.split()
        previous = tokens[-1].lstrip("(\"'“‘") if tokens else ""
        if previous.isalpha():
            lead = " ".join(tokens[:-1])
            mid_sentence = bool(lead) and lead[-1] not in _SENTENCE_END_CHARS
            if (
                previous.lower() in _MONTHS
                or previous.lower() in _TECH_LEXICON
                or (previous.isupper() and len(previous) >= 2)
                or (previous[0].isupper() and mid_sentence)
            ):
                return False
    tail = text[match.end() :]
    if _STREET_RE.match(tail):
        return False
    following = _FOLLOWING_WORDS_RE.match(tail)
    if not following:
        return False
    words = [word.lower() for word in following.groups() if word]
    if words[0] in _MONTHS:
        return False
    return any(len(word) >= 2 and word not in _NUMBER_STOPWORDS for word in words)


def _numeric_claims(text: str) -> list[_Claim]:
    masked = _GPA_RE.sub(_blank, _PHONE_RE.sub(_blank, text))
    claims: list[_Claim] = []
    for match in _CLAIM_RE.finditer(masked):
        surface = match.group(0).strip()
        if match.group("currency"):
            claims.append(
                _Claim("num", _to_number(match.group("currency_n"), match.group("currency_m")), match.start(), surface)
            )
        elif match.group("pct"):
            claims.append(_Claim("pct", _to_number(match.group("pct_n")), match.start(), surface))
        elif match.group("mult"):
            claims.append(_Claim("mult", _to_number(match.group("mult_n")), match.start(), surface))
        elif match.group("mag"):
            if match.group("mag_s") in {"k", "K"} and _SCREEN_WORD_RE.match(masked[match.end() :]):
                continue
            magnitude = match.group("mag_s") or match.group("mag_w")
            claims.append(_Claim("num", _to_number(match.group("mag_n"), magnitude), match.start(), surface))
        elif match.group("plus"):
            claims.append(_Claim("num", _to_number(match.group("plus_n")), match.start(), surface))
        else:
            raw = match.group("plain_n")
            value = _to_number(raw)
            if value < 10 or ("," not in raw and 1900 <= value <= 2100):
                continue
            if _counts_something(masked, match):
                claims.append(_Claim("num", value, match.start(), surface))
    return claims


def _number_index(corpus: str) -> dict[str, set[float]]:
    text = _CORPUS_THOUSANDS_RE.sub("", corpus.lower().replace("×", "x"))
    index: dict[str, set[float]] = {"pct": set(), "mult": set(), "num": set()}
    for match in _CORPUS_NUMBER_RE.finditer(text):
        value = _to_number(match.group("n"))
        index["num"].add(value)
        if match.group("pct"):
            index["pct"].add(value)
        elif match.group("mult"):
            index["mult"].add(value)
        elif match.group("mag"):
            index["num"].add(_to_number(match.group("n"), match.group("mag")))
    return index


def _check_unverified_number(context: _Context) -> list[_Finding]:
    if not context.evidence_corpus.strip():
        return []
    index = _number_index(context.evidence_corpus)
    seen: set[tuple[str, float]] = set()
    findings: list[_Finding] = []
    for unit in context.body:
        for claim in _numeric_claims(unit.text):
            key = (claim.cls, claim.value)
            if key in seen or claim.value in index[claim.cls]:
                continue
            seen.add(key)
            if len(findings) < _MAX_NUMBER_FINDINGS:
                findings.append(
                    _finding(
                        "unverified_number",
                        unit,
                        _excerpt(unit.text, claim.start, claim.start + len(claim.surface)),
                        f'"{claim.surface}" is not in the verified evidence. Confirm the figure with the candidate '
                        "or remove the precision; never invent metrics.",
                    )
                )
    return findings


def _is_ai_tell(label: str, text: str, match: re.Match[str]) -> bool:
    if label != "leverage":
        return True
    previous = _LAST_WORD_RE.search(text[: match.start()])
    following = _FIRST_WORD_RE.match(text[match.end() :])
    if previous and previous.group(1).lower() in _LEVERAGE_NOUN_LEADS:
        return False
    return not (following and following.group(1).lower() in _LEVERAGE_NOUN_TAILS)


def _check_ai_tell(context: _Context) -> list[_Finding]:
    findings: list[_Finding] = []
    for label, pattern in _AI_TELLS:
        hits: list[_Unit] = []
        first: tuple[_Unit, re.Match[str]] | None = None
        for unit in context.body:
            match = next((m for m in pattern.finditer(unit.text) if _is_ai_tell(label, unit.text, m)), None)
            if match:
                hits.append(unit)
                first = first or (unit, match)
        if first:
            unit, match = first
            finding = _finding(
                "ai_tell",
                unit,
                _excerpt(unit.text, match.start(), match.end()),
                f'"{match.group(0)}" reads as stock phrasing; say the specific thing in plain words.',
                where=_merged_where(hits),
            )
            findings.append(finding)
    return findings


def _tech_level(token: str, names: frozenset[str]) -> int:
    core = token.strip(_TOKEN_STRIP_CHARS)
    if core.endswith("."):
        core = core[:-1]
    lowered = core.lower()
    if lowered in _TECH_LEXICON:
        return 2
    if not core or not any(char.isalpha() for char in core) or lowered in names or lowered in _NON_TECH_TOKENS:
        return 0
    if _UNIT_TOKEN_RE.match(core):
        return 0
    if any(char.isdigit() or char in "+#." for char in core):
        return 2
    if core.isupper() and len(core) >= 2:
        return 2
    if core[0].isupper():
        return 2 if any(char.isupper() for char in core[1:]) else 1
    return 0


def _stack_inventory_start(text: str, names: frozenset[str]) -> int:
    for match in _STACK_TRIGGER_RE.finditer(text):
        count = 0
        strong = False
        for item in _STACK_SPLIT_RE.split(text[match.end() :]):
            tokens = item.split()
            level = _tech_level(tokens[0], names) if tokens else 0
            if not level:
                break
            count += 1
            strong = strong or any(_tech_level(token, names) > 1 for token in tokens[:3])
            if len(tokens) > 3:
                break
        if count >= 4 and (strong or match.group(1).lower() not in _STACK_STRICT_TRIGGERS):
            return match.start()
    tokens = text.split()
    levels = [_tech_level(token, names) for token in tokens[1:]]
    tech = sum(1 for level in levels if level)
    strong_count = sum(1 for level in levels if level > 1)
    if tech >= 4 and strong_count >= 2 and tech * 2 >= len(tokens) and "," in text:
        return 0
    return -1


def _check_weak_opener(context: _Context) -> list[_Finding]:
    return [
        _finding("weak_opener", unit, unit.text, "Lead with what you built or decided, then the consequence.")
        for unit in context.evidence_bullets
        if _WEAK_OPENER_RE.match(unit.text)
    ]


def _manufactured_ending(text: str) -> re.Match[str] | None:
    return None if _DIGIT_RE.search(text) else _MANUFACTURED_ENDING_RE.search(text)


def _check_manufactured_ending(context: _Context) -> list[_Finding]:
    findings: list[_Finding] = []
    for unit in context.evidence_bullets:
        match = _manufactured_ending(unit.text)
        if match:
            findings.append(
                _finding(
                    "manufactured_ending",
                    unit,
                    _excerpt(unit.text, match.start(), match.end()),
                    "Name the actual consequence (what shipped, what stopped failing, whose work changed) or cut "
                    "the ending.",
                )
            )
    return findings


def _check_stack_inventory(context: _Context) -> list[_Finding]:
    findings: list[_Finding] = []
    for unit in context.evidence_bullets:
        start = _stack_inventory_start(unit.text, context.names)
        if start >= 0:
            findings.append(
                _finding(
                    "stack_inventory",
                    unit,
                    _excerpt(unit.text, start, len(unit.text)),
                    "Keep only the technology needed to understand the mechanism; the Skills section carries the "
                    "inventory.",
                )
            )
    return findings


def _check_no_consequence(context: _Context) -> list[_Finding]:
    findings: list[_Finding] = []
    for unit in context.evidence_bullets:
        text = unit.text
        if _count_words(text) < 6 or _DIGIT_RE.search(text) or _CONSEQUENCE_RE.search(text):
            continue
        if (
            _WEAK_OPENER_RE.match(text)
            or _MANUFACTURED_ENDING_RE.search(text)
            or _stack_inventory_start(text, context.names) >= 0
        ):
            continue
        findings.append(
            _finding(
                "no_consequence",
                unit,
                text,
                "Consequence is implicit; state what changed because of this work (quantification optional).",
            )
        )
    return findings


def _first_person_start(text: str) -> int:
    starts: list[int] = []
    for match in _FIRST_PERSON_I_RE.finditer(text):
        if match.group(1):
            starts.append(match.start())
            break
        after = text[match.end() : match.end() + 2]
        if len(after) < 2 or after[0] != " " or not after[1].islower():
            continue
        before = text[: match.start()].rstrip()
        previous = before.split()[-1] if before else ""
        if not before or before[-1] in ".,;:!?—–(\"“" or previous[:1].islower():
            starts.append(match.start())
            break
    other = _FIRST_PERSON_OTHER_RE.search(text)
    if other:
        starts.append(other.start())
    return min(starts) if starts else -1


def _check_first_person(context: _Context) -> list[_Finding]:
    findings: list[_Finding] = []
    for unit in context.body:
        start = _first_person_start(unit.text)
        if start >= 0:
            findings.append(
                _finding(
                    "first_person",
                    unit,
                    _excerpt(unit.text, start, start),
                    "Resume lines are implied first person; drop the pronoun and lead with the verb.",
                )
            )
    return findings


def _lead_word(text: str) -> str:
    match = _FIRST_WORD_RE.match(text)
    return match.group(1) if match else ""


def _check_repeated_lead_verb(context: _Context) -> list[_Finding]:
    groups: dict[str, list[_Unit]] = {}
    for unit in context.evidence_bullets:
        lead = _lead_word(unit.text).lower()
        if lead:
            groups.setdefault(lead, []).append(unit)
    findings: list[_Finding] = []
    for lead, units in groups.items():
        if len(units) >= 3:
            findings.append(
                _finding(
                    "repeated_lead_verb",
                    units[0],
                    f'"{_lead_word(units[0].text)}" opens {len(units)} bullets',
                    "Vary the lead verb so each bullet names its own mechanism.",
                    where=_merged_where(units),
                )
            )
    return findings


def _check_bullet_length(context: _Context) -> list[_Finding]:
    findings: list[_Finding] = []
    for unit in context.evidence_bullets:
        words = _count_words(unit.text)
        if words > 45:
            fix = f"{words} words. Split or cut; one mechanism and one consequence per bullet."
        elif words < 6:
            fix = f"{words} words. Too thin to carry evidence."
        else:
            continue
        findings.append(_finding("bullet_length", unit, unit.text, fix))
    return findings


def _check_double_hyphen(context: _Context) -> list[_Finding]:
    if not context.writing.get("single_hyphen_ranges"):
        return []
    hits = [(unit, match) for unit in context.units if (match := _DOUBLE_HYPHEN_RE.search(unit.text))]
    if not hits:
        return []
    unit, match = hits[0]
    lines = sorted({hit.line for hit, _ in hits})
    shown = ", ".join(str(line) for line in lines[:_MAX_MERGED_POSITIONS])
    extra = len(lines) - _MAX_MERGED_POSITIONS
    where = _where(unit) if len(lines) == 1 else f"lines {shown}" + (f" +{extra} more" if extra > 0 else "")
    return [
        _finding(
            "double_hyphen",
            unit,
            _excerpt(unit.text, match.start(), match.end()),
            'Use a single hyphen for ranges ("2022 - 2024"); this profile does not use "--".',
            where=where,
        )
    ]


def _lead_tense(word: str) -> str:
    lowered = word.lower()
    if lowered in _PAST_IRREGULAR or (lowered.endswith("ed") and len(lowered) >= 4 and lowered not in _NOT_PAST):
        return "past"
    if lowered.endswith("ing") and len(lowered) >= 5 and lowered not in _NOT_GERUND:
        return "present"
    if lowered.endswith("s") and (lowered[:-1] in _PRESENT_VERB_BASES or lowered[:-2] in _PRESENT_VERB_BASES):
        return "present"
    return ""


def _check_tense_mix(context: _Context) -> list[_Finding]:
    bullets = context.evidence_bullets
    by_tense: dict[str, list[int]] = {"past": [], "present": []}
    for position, unit in enumerate(bullets):
        tense = _lead_tense(_lead_word(unit.text))
        if tense:
            by_tense[tense].append(position)
    majority, minority = "past", "present"
    if len(by_tense["present"]) > len(by_tense["past"]):
        majority, minority = minority, majority
    positions = by_tense[minority]
    if len(positions) < 2 or len(by_tense[majority]) < 0.7 * len(bullets):
        return []
    # One contiguous block in the other tense is usually a current role, which is conventional.
    if positions[-1] - positions[0] == len(positions) - 1:
        return []
    units = [bullets[position] for position in positions]
    return [
        _finding(
            "tense_mix",
            units[0],
            ", ".join(f'"{_lead_word(unit.text)}"' for unit in units),
            f"Most bullets open in the {majority} tense; align these unless they describe a current role.",
            where=_merged_where(units),
        )
    ]


def _check_generic_enthusiasm(context: _Context) -> list[_Finding]:
    findings: list[_Finding] = []
    for pattern in _GENERIC_ENTHUSIASM_RES:
        for unit in context.body:
            match = pattern.search(unit.text)
            if match:
                findings.append(
                    _finding(
                        "generic_enthusiasm",
                        unit,
                        _excerpt(unit.text, match.start(), match.end()),
                        f'"{match.group(0)}" could be sent to any employer; replace it with a specific reason '
                        "grounded in their work or your evidence.",
                    )
                )
                break
    return findings


def _name_key(text: str) -> str:
    return " ".join(_COMPANY_WORD_RE.findall(text.lower().replace("&", " and ")))


def _company_key(company: str) -> str:
    words = _name_key(company).split()
    while len(words) > 1 and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


def _check_company_missing(context: _Context) -> list[_Finding]:
    key = _company_key(context.company)
    if not key or f" {key} " in f" {_name_key(context.plain)} ":
        return []
    name = context.company.strip()
    return [
        _finding(
            "company_missing",
            None,
            f'"{name}" does not appear in the letter',
            f"Name {name} and tie at least one paragraph to its actual work.",
            kind=context.kind,
        )
    ]


def _check_jd_regurgitation(context: _Context) -> list[_Finding]:
    jd_tokens = [token.lower().replace("’", "'") for token in _RUN_WORD_RE.findall(context.job_description)]
    if len(jd_tokens) < _SHARED_RUN_WORDS:
        return []
    grams: dict[tuple[str, ...], list[int]] = {}
    for position in range(len(jd_tokens) - _SHARED_RUN_WORDS + 1):
        positions = grams.setdefault(tuple(jd_tokens[position : position + _SHARED_RUN_WORDS]), [])
        if len(positions) < _MAX_GRAM_POSITIONS:
            positions.append(position)
    runs: list[tuple[int, _Unit, str]] = []
    for unit in context.body:
        matches = list(_RUN_WORD_RE.finditer(unit.text))[:_MAX_RUN_UNIT_WORDS]
        tokens = [match.group(0).lower().replace("’", "'") for match in matches]
        best_length = 0
        best_start = 0
        for start in range(len(tokens) - _SHARED_RUN_WORDS + 1):
            if start + _SHARED_RUN_WORDS <= best_start + best_length:
                continue
            for jd_start in grams.get(tuple(tokens[start : start + _SHARED_RUN_WORDS]), ()):
                length = _SHARED_RUN_WORDS
                while (
                    start + length < len(tokens)
                    and jd_start + length < len(jd_tokens)
                    and tokens[start + length] == jd_tokens[jd_start + length]
                ):
                    length += 1
                if length > best_length:
                    best_length = length
                    best_start = start
        if best_length:
            quoted = unit.text[matches[best_start].start() : matches[best_start + best_length - 1].end()]
            runs.append((best_length, unit, quoted))
    runs.sort(key=lambda run: (-run[0], run[1].line))
    return [
        _finding(
            "jd_regurgitation",
            unit,
            quoted,
            f"{length} consecutive words match the posting. Rephrase in your own words and attach your own evidence.",
        )
        for length, unit, quoted in runs[:_MAX_REGURGITATION_FINDINGS]
    ]


def _letter_word_range(writing: dict[str, Any]) -> tuple[int, int]:
    value = writing.get("cover_letter_words")
    try:
        low, high = (int(part) for part in value)
    except (TypeError, ValueError):
        return _DEFAULT_LETTER_WORDS
    return (low, high) if 0 <= low <= high else _DEFAULT_LETTER_WORDS


def _check_letter_length(context: _Context) -> list[_Finding]:
    low, high = _letter_word_range(context.writing)
    words = context.body_words
    if low <= words <= high:
        return []
    return [
        _finding(
            "letter_length",
            None,
            f"{words} body words",
            f"Letter body is {words} words; the configured range is {low}-{high}. Length is diagnostic, not a "
            "target: cut filler or add missing evidence, never pad.",
            kind=context.kind,
        )
    ]


def _check_recital(context: _Context) -> list[_Finding]:
    paragraphs = context.paragraphs
    target: tuple[_Unit, str] | None = None
    for position, unit in enumerate(paragraphs):
        salutation = _SALUTATION_RE.match(unit.text)
        if not salutation:
            continue
        rest = unit.text[salutation.end() :].strip()
        if _count_words(rest) >= 3:
            target = (unit, rest)
        elif position + 1 < len(paragraphs):
            target = (paragraphs[position + 1], paragraphs[position + 1].text)
        break
    else:
        if paragraphs:
            target = (paragraphs[0], paragraphs[0].text)
    if not target or not _RECITAL_RE.match(target[1]):
        return []
    return [
        _finding(
            "opens_with_name_or_role_recital",
            target[0],
            target[1],
            "The header already says who you are; open with the work or problem that connects you to this role.",
        )
    ]


def _check_over_limit(context: _Context) -> list[_Finding]:
    if context.max_chars is None:
        return []
    limit = int(context.max_chars)
    length = len(context.plain)
    if context.fmt == "text":
        length = max(length, len(context.source.strip()))
    if length <= limit:
        return []
    return [
        _finding(
            "over_limit",
            None,
            f"{length} characters against a {limit}-character limit",
            f"Cut at least {length - limit} characters; the field rejects longer text.",
            kind=context.kind,
        )
    ]


def _check_stock_opener(context: _Context) -> list[_Finding]:
    findings: list[_Finding] = []
    for pattern in _STOCK_OPENER_RES:
        for unit in context.body:
            match = pattern.search(unit.text)
            if match:
                findings.append(
                    _finding(
                        "stock_opener",
                        unit,
                        _excerpt(unit.text, match.start(), match.end()),
                        f'Cut "{match.group(0)}" and open with the specific reason you are writing to this person.',
                    )
                )
                break
    return findings


def _check_too_long(context: _Context) -> list[_Finding]:
    words = context.body_words
    if words < _OUTREACH_NOTE_WORDS:
        return []
    over = words > _OUTREACH_MAX_WORDS
    return [
        _finding(
            "too_long",
            None,
            f"{words} words",
            f"First-contact messages read best under {_OUTREACH_NOTE_WORDS} words"
            f" (hard ceiling {_OUTREACH_MAX_WORDS}): one line of context, one piece of evidence, one ask.",
            severity="warning" if over else "note",
            kind=context.kind,
        )
    ]


def _check_no_clear_ask(context: _Context) -> list[_Finding]:
    text = " ".join(unit.text for unit in context.body)
    if not text or _CLEAR_ASK_RE.search(text):
        return []
    substantial = [unit.text for unit in context.body if _count_words(unit.text) >= 6]
    closing = substantial[-1] if substantial else text
    sentences = [sentence for sentence in _SENTENCE_SPLIT_RE.split(closing) if _ALNUM_RE.search(sentence)]
    return [
        _finding(
            "no_clear_ask",
            None,
            sentences[-1] if sentences else closing,
            "End with one specific, easy-to-answer ask.",
            kind=context.kind,
        )
    ]


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TERM_RE.finditer(text.lower()):
        token = match.group(0).rstrip(".")
        if len(token) >= 2 and any(char.isalpha() for char in token):
            tokens.append(token)
    return tokens


def _stem(token: str) -> str:
    if len(token) < 4 or not token.isalpha():
        return token
    word = token
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "y"
    elif word.endswith("s") and not word.endswith(("ss", "us")) and not (word.endswith("is") and len(word) > 4):
        word = word[:-1]
    if word.endswith("ing") and len(word) >= 6:
        word = word[:-3]
    elif word.endswith("ed") and len(word) >= 6:
        word = word[:-2]
    elif word.endswith("ed") and len(word) == 5:
        word = word[:-1]
    if word.endswith("e") and len(word) >= 4:
        word = word[:-1]
    if len(word) >= 4 and word[-1] == word[-2] and word[-1] not in "aeiou":
        word = word[:-1]
    return word


def _content_terms(text: str) -> dict[str, str]:
    terms: dict[str, str] = {}
    for token in _tokens(text):
        if token not in _STOPWORDS:
            terms.setdefault(_stem(token), token)
    return terms


def _jd_terms_missing(job_description: str, material: set[str], names: frozenset[str]) -> list[str]:
    counts: dict[str, int] = {}
    surfaces: dict[str, str] = {}
    technical: set[str] = set()
    for line in _JD_STATE_CODE_RE.sub(" ", job_description).splitlines():
        matches = list(_TERM_RE.finditer(line))
        heading_like = len(matches) <= 5 and not _JD_SENTENCE_PUNCT_RE.search(line)
        for match in matches:
            raw = match.group(0).rstrip(".")
            token = raw.lower()
            if len(token) < 2 or not any(char.isalpha() for char in token):
                continue
            if token in _STOPWORDS or token in names:
                continue
            stem = _stem(token)
            counts[stem] = counts.get(stem, 0) + 1
            surfaces.setdefault(stem, token)
            acronym = raw.isupper() and raw.isalpha() and 2 <= len(raw) <= 6 and token not in _JD_NON_SKILL_ACRONYMS
            mixed_case = raw != token and not raw.isupper() and any(char.isupper() for char in raw[1:])
            if token in _JD_NON_SKILL_ACRONYMS and not _TECH_CHARS_RE.search(raw):
                continue
            if token in _JD_SKILL_LEXICON or _TECH_CHARS_RE.search(raw) or mixed_case or (acronym and not heading_like):
                technical.add(stem)
    missing = [stem for stem in counts if stem not in material and stem in technical]
    missing.sort(key=lambda stem: (-counts[stem], surfaces[stem]))
    return [surfaces[stem] for stem in missing[:_MAX_JD_TERMS]]


def _coverage(context: _Context) -> dict[str, Any] | None:
    job_description = context.job_description.strip()
    if not context.requirements and not job_description:
        return None
    material = {_stem(token) for token in _tokens(context.plain)}
    coverage: dict[str, Any] = {}
    if context.requirements:
        covered = 0
        uncovered: list[dict[str, Any]] = []
        for requirement in context.requirements:
            terms = _content_terms(requirement)
            missing = [surface for stem, surface in terms.items() if stem not in material]
            matched = len(terms) - len(missing)
            if not terms or (matched >= 1 and matched * 2 >= len(terms)):
                covered += 1
            else:
                uncovered.append(
                    {
                        "requirement": _clip(requirement, _REQUIREMENT_LIMIT),
                        "missing_terms": missing[:_MAX_MISSING_TERMS],
                    }
                )
        coverage["requirements_covered"] = covered
        coverage["requirements_total"] = len(context.requirements)
        coverage["uncovered"] = uncovered
    if job_description:
        coverage["jd_terms_missing"] = _jd_terms_missing(job_description, material, context.company_words)
    coverage["note"] = _COVERAGE_NOTE
    return coverage


_RESUME = ("resume",)
_LETTER = ("cover_letter",)
_ANSWERS = ("application_answers",)
_OUTREACH = ("outreach",)

_RULES: tuple[_Rule, ...] = (
    _Rule("scaffolding_leak", "error", KINDS, _check_scaffolding_leak),
    _Rule("unverified_number", "warning", KINDS, _check_unverified_number),
    _Rule("ai_tell", "note", KINDS, _check_ai_tell),
    _Rule("weak_opener", "warning", _RESUME, _check_weak_opener),
    _Rule("manufactured_ending", "warning", _RESUME, _check_manufactured_ending),
    _Rule("stack_inventory", "warning", _RESUME, _check_stack_inventory),
    _Rule("no_consequence", "note", _RESUME, _check_no_consequence),
    _Rule("first_person", "warning", _RESUME, _check_first_person),
    _Rule("repeated_lead_verb", "note", _RESUME, _check_repeated_lead_verb),
    _Rule("bullet_length", "note", _RESUME, _check_bullet_length),
    _Rule("double_hyphen", "warning", _RESUME, _check_double_hyphen),
    _Rule("tense_mix", "note", _RESUME, _check_tense_mix),
    _Rule("generic_enthusiasm", "warning", _LETTER + _ANSWERS + _OUTREACH, _check_generic_enthusiasm),
    _Rule("company_missing", "warning", _LETTER, _check_company_missing),
    _Rule("jd_regurgitation", "warning", _LETTER, _check_jd_regurgitation),
    _Rule("letter_length", "note", _LETTER, _check_letter_length),
    _Rule("opens_with_name_or_role_recital", "note", _LETTER, _check_recital),
    _Rule("over_limit", "error", _ANSWERS, _check_over_limit),
    _Rule("stock_opener", "warning", _OUTREACH, _check_stock_opener),
    _Rule("too_long", "warning", _OUTREACH, _check_too_long),
    _Rule("no_clear_ask", "note", _OUTREACH, _check_no_clear_ask),
)
_SEVERITIES = {rule.id: rule.severity for rule in _RULES}

RULE_IDS: tuple[str, ...] = tuple(rule.id for rule in _RULES)
