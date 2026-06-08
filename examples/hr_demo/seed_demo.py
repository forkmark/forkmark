"""
Forkmark HR Demo — Job Description Generator
==============================================

Workflow:  job-description-generator
Eval run:  Inclusive Role-Specific Prompt v2 vs Generic Template v1
Branches:
  A — Inclusive Role-Specific Prompt v2  (baseline — wins this eval)
  B — Generic Template v1                (challenger — boilerplate output)

10 role cases × 4 steps each:
  role_overview · key_responsibilities · required_qualifications · benefits_culture

Run:   python seed_demo.py
Then:  open http://localhost:5173
"""

import httpx
import time, sys, os
BASE_URL = "http://localhost:7700"
_api_key = os.environ.get("FORKMARK_API_KEY", "")
HEADERS  = {"Content-Type": "application/json"}
if _api_key:
    HEADERS["X-API-Key"] = _api_key


def api(method, path, data=None, _retries=4, _backoff=1.0):
    url = BASE_URL + path
    for attempt in range(_retries):
        try:
            r = getattr(httpx, method)(url, json=data, headers=HEADERS, timeout=10)
            if r.status_code == 429:
                wait = _backoff * (2 ** attempt)
                print(f"  [rate-limit] backing off {wait:.1f}s before retry {attempt+1}/{_retries-1}...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            print(f"\n[error] Cannot connect to {BASE_URL}")
            print("  Make sure Forkmark is running (run `python run.py` first)\n")
            sys.exit(1)
        except Exception as e:
            print(f"[error] {method.upper()} {path}: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"  Response: {e.response.text[:200]}")
            return None
    print(f"[error] {method.upper()} {path}: rate limit retries exhausted")
    return None


CASES = [
    {
        "label": "senior-software-engineer",
        "brief": "Senior SWE, backend focus, Python/Go, distributed systems, fintech startup, 150-200 employees, Series B, remote-first.",
        "ro_a": "We're building the infrastructure that moves money for millions of people — and we need engineers who care about getting it right. As a Senior Software Engineer on our backend platform team, you'll design and own distributed systems that process billions of pounds in transactions each year. This isn't a role for people who want to maintain existing code — it's for engineers who want to fundamentally shape how a fast-scaling fintech operates.",
        "ro_b": "We are looking for a Senior Software Engineer to join our team. You will be responsible for designing and implementing software solutions. The ideal candidate will have strong technical skills and the ability to work in a team environment.",
        "kr_a": "• Design, build, and operate core backend services in Python and Go handling high-throughput payment processing\n• Lead technical design reviews and set engineering standards for a squad of 4-6 engineers\n• Drive system reliability: contribute to on-call rotations and own SLO/SLA definitions for your services\n• Collaborate with product and data teams to translate business requirements into scalable architecture\n• Champion engineering practices: code review, observability, and incident retrospectives",
        "kr_b": "• Develop and maintain software applications\n• Write clean, efficient code\n• Participate in code reviews\n• Collaborate with cross-functional teams\n• Debug and resolve technical issues",
        "rq_a": "We care about what you can do, not where you've been. That said, you'll likely have: 5+ years building production backend systems in Python and/or Go; experience with distributed systems, event-driven architecture, or payment systems; a track record of designing for scale (we process 10K+ TPS at peak); comfort owning services end-to-end — from design through production support. No CS degree required — we hire on demonstrated ability.",
        "rq_b": "• Bachelor's degree in Computer Science or related field\n• 5+ years of software development experience\n• Proficiency in Python and Go\n• Experience with distributed systems\n• Strong communication skills",
        "bc_a": "Remote-first with optional hubs in London and Amsterdam. Salary: £120,000–£150,000 + equity (0.1–0.3% options at Series B valuation). 35 days' holiday. £3,000/year learning budget. Private health (Bupa), dental, and enhanced parental leave (26 weeks full pay for all parents). We sponsor visas. We're committed to building a team that reflects the diversity of the people we serve — we particularly welcome applicants from underrepresented groups in tech.",
        "bc_b": "• Competitive salary and benefits\n• Health insurance\n• 25 days holiday\n• Career development opportunities\n• Dynamic work environment",
    },
    {
        "label": "data-scientist-ml",
        "brief": "Data Scientist, ML focus, recommendation engine, e-commerce, 500 employees, profitable, hybrid London.",
        "ro_a": "Our recommendation engine drives 34% of revenue — and we're rebuilding it from the ground up. As a Data Scientist on our Personalisation team, you'll own the modelling work that determines what 2 million customers see every time they visit our platform. You'll work in a team that has real influence: your models go live within weeks, not quarters, and you'll see their impact in revenue dashboards the day after deployment.",
        "ro_b": "We are seeking a talented Data Scientist to join our growing team. You will use data to drive insights and build models that improve our business outcomes.",
        "kr_a": "• Build and iterate on collaborative filtering and content-based recommendation models using Python (PyTorch, scikit-learn)\n• Design and run A/B experiments to validate model improvements — own experiment design, stat significance, and stakeholder reporting\n• Work closely with data engineering to ensure training data pipelines are reliable and reproducible\n• Develop offline and online evaluation frameworks — uplift, NDCG, revenue impact\n• Present findings and model decisions to non-technical stakeholders including the CPO",
        "kr_b": "• Analyse large datasets to extract insights\n• Build machine learning models\n• Collaborate with engineering and product teams\n• Communicate findings to stakeholders\n• Stay up to date with ML advancements",
        "rq_a": "You'll thrive here if you have: 3+ years building and shipping production ML models (not just Jupyter notebooks); hands-on experience with recommendation systems or ranking models; strong statistical grounding — you can design an A/B test, explain p-values without jargon, and spot Simpson's paradox in the wild; Python fluency (pandas, scikit-learn, PyTorch or TF). Bonus: experience with real-time serving or feature stores. No PhD required — we hire on shipped work.",
        "rq_b": "• Degree in Data Science, Statistics, or Computer Science\n• 3+ years of data science experience\n• Proficiency in Python and SQL\n• Experience with machine learning frameworks\n• Strong analytical skills",
        "bc_a": "Hybrid: 2 days/week in our Shoreditch office, 3 remote. Salary: £75,000–£100,000 + annual bonus (10-15%). 28 days holiday + bank holidays. £2,000 annual conference and learning budget — we actively encourage publishing and speaking. Flexible working hours. Cycle-to-work scheme. We're a Disability Confident Employer and make adjustments throughout our hiring process — please let us know what you need.",
        "bc_b": "• Competitive salary\n• Flexible working arrangements\n• Training and development budget\n• Health and wellness benefits\n• Supportive team environment",
    },
    {
        "label": "product-manager",
        "brief": "Product Manager, B2B SaaS, workflow automation product, 80 employees, Seed/Series A, London hybrid.",
        "ro_a": "We're building the workflow automation layer for operations teams — and we're at the stage where the PM we hire will define the product direction for the next two years. This is a high-autonomy role: you'll own the roadmap for our core automation engine, work directly with our 15 design customers to distil their needs into a product vision, and partner with a 6-person engineering squad to ship it. No PM bureaucracy, no committee decisions — just you, fast feedback loops, and real customers.",
        "ro_b": "We are hiring a Product Manager to drive the development of our software products. You will work with engineering, design, and business teams to deliver features that meet customer needs.",
        "kr_a": "• Own the roadmap for our workflow automation engine — from discovery through delivery and iteration\n• Conduct regular customer interviews (weekly during discovery phases) to deeply understand workflow pain points\n• Write clear product specs and acceptance criteria — you bridge the gap between customer need and engineering implementation\n• Define and track product KPIs; run lightweight experiments to validate assumptions before committing engineering time\n• Represent the product in commercial conversations — support sales with technical product knowledge",
        "kr_b": "• Define product requirements and roadmap\n• Work with engineering teams to deliver features\n• Gather customer feedback\n• Prioritise backlog items\n• Track product performance metrics",
        "rq_a": "You'll be great here if you have: 3+ years as a PM at a B2B SaaS company (ideally with a technical product — workflow, automation, APIs, or infrastructure); a track record of shipping product that customers actually use (show us something you shipped and what you learned); comfort going deep with customers — you've run discovery interviews, not just surveys. Bonus: you've worked at a company in the 10–100 person range and know what 'doing things that don't scale' means in practice.",
        "rq_b": "• 3+ years product management experience\n• Experience in B2B SaaS\n• Strong communication and leadership skills\n• Ability to work in a fast-paced environment\n• Data-driven decision making",
        "bc_a": "Hybrid: 3 days/week in our Clerkenwell office. Salary: £70,000–£90,000 + 0.25–0.5% equity at current valuation. 28 days holiday. Quarterly team off-sites. £1,500/year personal development budget. We're a small team and we're intentional about culture — we have a weekly Friday retrospective that includes the whole company, and our CEO reads every customer interview transcript. We don't have formal processes for most things because we're not big enough to need them yet.",
        "bc_b": "• Competitive compensation package\n• Equity participation\n• Flexible working options\n• Professional development support\n• Collaborative company culture",
    },
    {
        "label": "sales-director",
        "brief": "Sales Director, enterprise SaaS, cybersecurity, 300 employees, Series C, US market, remote.",
        "ro_a": "We've built a cybersecurity platform that CISO teams love — and we need someone who can take it to enterprise at scale. As Sales Director for North America, you'll own a $15M ARR target and build the team to get there. This isn't a 'player-coach' title — you'll close the flagship enterprise deals yourself while hiring and developing a team of 6 AEs. The deals are complex (6-12 month cycles, $200K-$2M ACV), the product is genuinely differentiated, and the market is on fire.",
        "ro_b": "We are looking for a Sales Director to lead our sales efforts. You will be responsible for driving revenue growth and managing a team of sales professionals.",
        "kr_a": "• Own and exceed the $15M ARR North America target\n• Personally close 4-6 enterprise flagship accounts per year ($500K+ ACV) while enabling the team\n• Hire, ramp, and develop a team of 6 Account Executives (currently 2 in place)\n• Build enterprise sales motion: champion mapping, multi-threading, executive sponsorship\n• Work with marketing and SDR teams to develop enterprise pipeline — own the top-of-funnel quality for your segment\n• Report directly to the CRO; contribute to company-level go-to-market strategy",
        "kr_b": "• Lead and manage the sales team\n• Develop sales strategies to achieve revenue targets\n• Build relationships with key clients\n• Manage the full sales cycle\n• Report on sales performance",
        "rq_a": "We're looking for someone who has: 8+ years in enterprise SaaS sales, with 3+ years in a sales leadership role; a track record of personally closing $500K+ ACV deals — we'll ask you to walk us through a specific deal in the interview; experience building and scaling AE teams (not just inheriting one); comfort selling into security/IT buyer personas — CISO, CTO, VP Engineering. Bonus: cybersecurity or adjacent technical domain background. We don't care about credentials — we care about closed revenue and how you got there.",
        "rq_b": "• 8+ years of sales experience\n• Proven track record of meeting sales targets\n• Experience leading sales teams\n• Strong negotiation skills\n• Excellent communication abilities",
        "bc_a": "Remote (US-based, with quarterly travel to our San Francisco HQ). OTE: $280,000–$340,000 (50/50 split, uncapped accelerators above 100% quota). RSUs with 4-year vest and 1-year cliff. Unlimited PTO with a minimum floor of 15 days enforced. Premium healthcare (medical, dental, vision) for employee and dependants. We're building a diverse sales leadership team — we especially encourage applications from women and underrepresented groups in cybersecurity.",
        "bc_b": "• Competitive base salary plus commission\n• Equity package\n• Health and dental benefits\n• Flexible remote working\n• Career progression opportunities",
    },
    {
        "label": "marketing-manager",
        "brief": "Marketing Manager, content and demand gen, B2B HR tech, 120 employees, growth stage, London hybrid.",
        "ro_a": "We help HR teams run better — and your job is to help them find us. As Marketing Manager, you'll own the content and demand generation engine for a company that's growing 80% year-over-year and has just landed its first enterprise accounts. You'll have a £200K annual budget, a small team of two (a content writer and a paid media specialist), and the autonomy to experiment. If you've ever wanted to build a marketing function from a decent foundation rather than starting from scratch, this is that role.",
        "ro_b": "We are seeking a Marketing Manager to oversee our marketing activities. You will develop and implement marketing strategies to promote our products and services.",
        "kr_a": "• Own the content marketing programme: editorial calendar, SEO strategy, long-form content (guides, reports, case studies) and distribution\n• Run demand generation: manage paid LinkedIn and Google campaigns, own MQL targets and cost-per-lead\n• Build the analyst and press relations function — get us in Gartner, Forrester, and HR trade press\n• Partner with sales on ABM campaigns for target accounts (we have a list of 50)\n• Report on marketing contribution to pipeline weekly; own Marketing attribution in HubSpot",
        "kr_b": "• Develop and execute marketing campaigns\n• Manage social media and content\n• Coordinate with sales team\n• Track and report on marketing KPIs\n• Manage marketing budget",
        "rq_a": "You'll be the right fit if you have: 4+ years in B2B marketing with at least 2 in a role owning demand gen or content; demonstrable pipeline contribution — you can show us MQL-to-SQL conversion rates and marketing-sourced revenue; hands-on paid media experience (LinkedIn Campaign Manager is essential); HubSpot or equivalent CRM/MAP fluency. HR tech experience is a bonus but not required — we care more about B2B marketing craft. We welcome applications from returners and career changers.",
        "rq_b": "• 4+ years marketing experience\n• B2B marketing background preferred\n• Knowledge of digital marketing channels\n• Experience with CRM and marketing automation tools\n• Strong written communication skills",
        "bc_a": "Hybrid: 2-3 days/week in our Vauxhall office. Salary: £55,000–£70,000 + annual bonus (up to 15%). 28 days holiday + bank holidays. £1,500 marketing conference budget (separate from personal learning budget). Flexible start/end times — core hours 10am-4pm. Enhanced parental leave (18 weeks full pay). We actively benchmark salaries against market data every 6 months and share the results with the whole company.",
        "bc_b": "• Competitive salary\n• Bonus scheme\n• Holiday entitlement\n• Learning and development budget\n• Friendly working environment",
    },
    {
        "label": "devops-engineer",
        "brief": "DevOps/Platform Engineer, AWS, Kubernetes, Terraform, healthcare SaaS, 200 employees, Series B, remote UK.",
        "ro_a": "Our platform processes patient data for 300 NHS trusts — reliability isn't optional. As a Platform Engineer, you'll own the infrastructure that keeps a healthcare-critical SaaS running at 99.95% uptime across multi-region AWS. You'll be working with a team of 4 platform engineers, supporting 40 product engineers, and building the automation that means nobody has to do the same manual task twice. If you want infrastructure where the stakes are real and the work is genuinely complex, this is it.",
        "ro_b": "We are looking for a DevOps Engineer to manage and improve our infrastructure. You will be responsible for CI/CD pipelines, cloud infrastructure, and system reliability.",
        "kr_a": "• Own and improve our AWS multi-region Kubernetes infrastructure (EKS) — we're running 200+ microservices\n• Build and maintain Terraform modules for all infrastructure provisioning — we're 95% IaC already\n• Improve CI/CD pipelines (GitHub Actions) — current deploy time is 18 minutes, target is under 8\n• Own observability: Datadog dashboards, alert tuning, and on-call runbooks (PagerDuty)\n• Drive security compliance: we're ISO 27001 certified and working towards Cyber Essentials Plus\n• Support product engineers — you're their first call when production behaves unexpectedly",
        "kr_b": "• Manage cloud infrastructure on AWS\n• Maintain CI/CD pipelines\n• Configure and monitor Kubernetes clusters\n• Write infrastructure as code using Terraform\n• Collaborate with development teams",
        "rq_a": "We're looking for someone with: 3+ years hands-on AWS infrastructure experience (EKS, RDS, VPC, IAM — not just EC2 and S3); Terraform proficiency — you've written modules, not just applied plans; Kubernetes operational experience — debugging CrashLoopBackoff at 2am is a thing you've done; comfort with observability tooling (Datadog, Prometheus, or similar). Bonus: NHS/healthcare compliance experience, or any regulated-sector infrastructure background. We have an accessible hiring process — tell us what you need.",
        "rq_b": "• 3+ years DevOps or cloud infrastructure experience\n• AWS certification preferred\n• Kubernetes and Docker knowledge\n• Experience with Terraform\n• Good problem-solving skills",
        "bc_a": "Fully remote (UK-based). Salary: £70,000–£90,000 + annual performance bonus. 33 days holiday (including bank holidays). Home office setup budget (£1,500 on joining). Internet allowance £50/month. Private healthcare (AXA) and dental. We're on-call but we do it properly: PagerDuty schedule, on-call allowance (£300/month), and we do blameless post-mortems — no hero culture. We take accessibility seriously in our hiring and our product.",
        "bc_b": "• Competitive salary\n• Remote working\n• Private healthcare\n• Annual leave\n• Professional certifications support",
    },
    {
        "label": "customer-success-manager",
        "brief": "Customer Success Manager, mid-market SaaS, project management tool, 60 employees, Series A, London hybrid.",
        "ro_a": "Churn is a solved problem if you do CS right — and this role is your chance to prove it. As Customer Success Manager, you'll own a portfolio of 40 mid-market accounts (£50K–£200K ARR each) and be responsible for their health, adoption, and expansion. You'll be the first dedicated CSM at the company — which means you get to define what great CS looks like here, not inherit a playbook someone else wrote. You'll report directly to the CEO for the first 6 months.",
        "ro_b": "We are looking for a Customer Success Manager to manage client relationships and ensure customer satisfaction. You will work with customers to maximise the value they receive from our product.",
        "kr_a": "• Own a portfolio of 40 mid-market accounts — net revenue retention is your north star metric (target: 115%)\n• Run structured onboarding programmes for new customers — time-to-value is currently 45 days, target is under 30\n• Conduct quarterly business reviews (QBRs) with economic buyers, not just day-to-day users\n• Identify and close expansion opportunities — coordinate with sales on upsell and cross-sell\n• Build the CS playbook from scratch: health scores, risk triggers, escalation paths, QBR templates\n• Be the voice of the customer internally: feed insights to product with specifics, not generalities",
        "kr_b": "• Manage customer relationships and ensure satisfaction\n• Conduct regular check-ins with clients\n• Identify opportunities to upsell\n• Handle customer issues and escalations\n• Track customer health metrics",
        "rq_a": "You'll do well here if you have: 3+ years in customer success at a B2B SaaS company; a portfolio you can talk about — NRR numbers, how you turned around a churning account, what your QBR structure looked like; commercial instinct — CS is a revenue function here, not just a support function; comfort operating without a full playbook — you've built things, not just followed them. Project management software experience is a nice bonus but not required.",
        "rq_b": "• 3+ years customer success experience\n• Strong relationship management skills\n• Experience with SaaS products\n• Excellent communication abilities\n• Problem-solving mindset",
        "bc_a": "Hybrid: 2 days/week in our Bermondsey office (great coffee, average foosball). Salary: £50,000–£65,000 + quarterly bonus tied to NRR. 28 days holiday. Wellbeing budget: £500/year for anything that keeps you healthy and sane. Mental health support via Spill. We're a team of 60 and we're deliberately building culture before we scale — monthly team lunches, an annual company trip, and no meeting Fridays. We're actively working on our diversity — currently 40% women in leadership, aiming for parity by end of year.",
        "bc_b": "• Competitive salary and bonus\n• Flexible working\n• Holiday allowance\n• Team social events\n• Career growth opportunities",
    },
    {
        "label": "finance-analyst",
        "brief": "Finance Analyst, FP&A focus, private equity-backed retail, 1200 employees, cost transformation programme.",
        "ro_a": "We're 18 months into a PE-backed transformation and the Finance team is at the centre of it. As Finance Analyst in our FP&A team, you'll be building the models that drive cost reduction decisions affecting 1,200 employees and 80 stores. This isn't a reporting role — it's a role where your analysis directly informs where we cut, where we invest, and how we tell the story to our board and PE sponsors. You'll have a direct line to the CFO and present to the board quarterly.",
        "ro_b": "We are looking for a Finance Analyst to support our financial planning and analysis activities. You will help with financial reporting, modelling, and forecasting.",
        "kr_a": "• Build and maintain the group P&L model and 3-year plan — you own the file, not just inputs to it\n• Lead monthly management accounts pack (P&L, BS, cash): variance analysis, commentary, board-ready output\n• Own store-level profitability analysis — identifying the bottom quartile and modelling closure/restructure scenarios\n• Develop the cost transformation tracker: £15M target over 24 months, reported to PE sponsors monthly\n• Partner with commercial and ops teams to provide financial analysis for major decisions (new store openings, supplier renegotiations, headcount reviews)\n• Support the CFO on ad-hoc analysis for PE reporting and board papers",
        "kr_b": "• Prepare financial reports and analysis\n• Support budgeting and forecasting processes\n• Analyse variances and identify trends\n• Work with business units to gather financial data\n• Assist with month-end close",
        "rq_a": "We're looking for someone with: 2-4 years in FP&A, management consulting, or a similar analytical finance role; advanced Excel and financial modelling skills — we'll ask you to build something in the interview; comfort with ambiguity — our data estate is imperfect and we need someone who can work with what we have; a degree or ACA/CIMA/ACCA qualification (or equivalent progress). PE-backed or retail experience is a bonus. We're open to applications from people returning from career breaks.",
        "rq_b": "• Degree in Finance, Accounting, or related field\n• 2-4 years financial analysis experience\n• Advanced Excel skills\n• Professional qualification working towards or achieved\n• Attention to detail",
        "bc_a": "London office (Paddington), hybrid — core expectation 3 days in during month-end, 2 days other weeks. Salary: £45,000–£58,000 + discretionary bonus. 25 days holiday + bank holidays (rising to 28 after 2 years). ACA/CIMA study support: fees, study leave, and a pass bonus. Private healthcare (Vitality) from day one. We're a transformation business, which means it's intense — we're honest about that. In return, the exposure and pace of learning here is genuinely unusual for an analyst-level role.",
        "bc_b": "• Competitive salary\n• Study support for professional qualifications\n• Private healthcare\n• Annual leave\n• Pension contributions",
    },
    {
        "label": "ux-designer",
        "brief": "UX Designer, mid-level, mobile-first consumer app, fintech, 70 employees, Series A, London hybrid.",
        "ro_a": "We have 500,000 users who open our app every day — and every pixel you design will be used by real people managing real money. As a UX Designer on our product team, you'll own the end-to-end design of our mobile features (iOS and Android), from discovery research through Figma prototypes to shipped components in our design system. You'll be the second designer at the company, working alongside our Head of Design and 4 PMs. Your work will ship within weeks of design completion.",
        "ro_b": "We are looking for a UX Designer to create intuitive and visually appealing user interfaces. You will work with our product and engineering teams to deliver excellent user experiences.",
        "kr_a": "• Own the full design lifecycle for 1-2 product features at a time: user research, wireframes, hi-fi prototypes, and design QA\n• Conduct and analyse 8-10 user research sessions per quarter — moderated interviews, usability tests, and card sorts\n• Design for accessibility: all features ship WCAG 2.1 AA compliant — you own this, not the engineers\n• Contribute to and evolve the design system (Figma, 200+ components) — you'll add ~20 components per quarter\n• Work with engineers daily — you attend sprint ceremonies and handle design questions in real-time\n• Use data: you have access to Amplitude and FullStory and you use them to validate decisions, not just justify them",
        "kr_b": "• Create wireframes, prototypes, and high-fidelity designs\n• Conduct user research and usability testing\n• Collaborate with product and engineering teams\n• Maintain design consistency across the product\n• Stay current with UX trends and best practices",
        "rq_a": "We'd love to hear from you if you have: 3+ years UX design experience with a portfolio that shows your process, not just final screens — we'll ask about research findings that changed your design; strong Figma skills (components, auto-layout, variants — not just drawing rectangles); mobile design experience; WCAG/accessibility knowledge. Bonus: fintech or financial product background. We're committed to an inclusive hiring process — if you need any adjustments, please ask.",
        "rq_b": "• 3+ years UX design experience\n• Proficiency in Figma or similar design tools\n• Portfolio demonstrating UX projects\n• Knowledge of user research methods\n• Strong visual design skills",
        "bc_a": "Hybrid: 2-3 days/week in our London Bridge office. Salary: £55,000–£70,000. 28 days holiday + bank holidays. £1,500/year learning budget (conferences, courses, books — your choice). Equipment of your choice on joining. We support flexible working hours: 10am-4pm core, build your day around them. We're working to improve representation in design — we currently have 3 designers and 2 of 3 are women; we're actively encouraging applications from designers of colour and disabled designers.",
        "bc_b": "• Competitive salary\n• Flexible working\n• Learning and development opportunities\n• Modern office environment\n• Health benefits",
    },
    {
        "label": "operations-manager",
        "brief": "Operations Manager, logistics/fulfilment, e-commerce, 400 employees, 3PL environment, Birmingham, on-site.",
        "ro_a": "We ship 25,000 orders a day out of our Birmingham fulfilment centre — and we need an Operations Manager who can make 25,000 feel like 250,000. This is a hands-on, floor-level leadership role: you'll manage a team of 120 warehouse operatives across 3 shifts, own the pick-pack-dispatch KPIs, and lead continuous improvement projects that shave seconds off per-unit costs. If you want a role where you can see the results of your decisions the same day you make them, this is it.",
        "ro_b": "We are seeking an Operations Manager to oversee our warehouse and fulfilment operations. You will manage staff, processes, and ensure efficient order fulfilment.",
        "kr_a": "• Lead 120 warehouse operatives across day, late, and night shifts — including 6 team leaders who report to you\n• Own daily KPIs: units per hour, pick accuracy (target 99.8%), on-time dispatch, and cost-per-order\n• Drive continuous improvement: you'll run 2-3 Kaizen/lean improvement projects per year — last year's saved £280K\n• Manage 3PL relationships: we work with 2 carrier partners (DHL, Evri) and your team owns the SLA\n• Lead the agency workforce management process: we flex from 80 to 180 headcount seasonally\n• Report directly to the Head of Logistics with a dotted line to the COO during peak periods",
        "kr_b": "• Oversee daily warehouse and fulfilment operations\n• Manage and develop a team of warehouse staff\n• Monitor and improve operational KPIs\n• Coordinate with logistics partners\n• Implement process improvements",
        "rq_a": "You'll be great here if you have: 4+ years in warehouse or fulfilment operations management, including direct team leadership; experience managing 50+ direct and indirect reports; hands-on lean/continuous improvement experience — you've run a project, not just attended a training; comfort with WMS systems (we use Manhattan Associates); a track record of hitting pick accuracy and cost-per-order targets. Bonus: e-commerce or 3PL experience. We're a 24/7 operation and expect the role to require occasional weekend presence during peak (Oct-Dec).",
        "rq_b": "• 4+ years warehouse management experience\n• Team leadership experience\n• Knowledge of warehouse management systems\n• Strong organisational skills\n• Ability to work under pressure",
        "bc_a": "On-site, Birmingham (B6 — accessible via Aston train station and multiple bus routes). Salary: £45,000–£55,000 + annual bonus (up to £5,000 based on KPI achievement). 28 days holiday. Company pension (6% employer contribution). Free on-site parking. Canteen subsidy. Overtime available at premium rate during peak. We have a structured career path: Operations Manager → Senior Operations Manager → Head of Site — we promoted 3 internal OMs to Head of Site in the last 2 years. We're working on increasing gender and ethnic diversity at management level and welcome applicants from all backgrounds.",
        "bc_b": "• Competitive salary and bonus\n• Company pension\n• 28 days holiday\n• On-site parking\n• Career progression opportunities",
    },
]


def check_backend():
    print("[check] Connecting to Forkmark backend...")
    try:
        r = httpx.get(BASE_URL + "/api/stats", timeout=5)
        r.raise_for_status()
        print(f"[check] ✓ Backend reachable at {BASE_URL}")
    except Exception:
        print(f"\n[error] Cannot reach {BASE_URL}/api/stats")
        print("  Make sure the Forkmark backend is running:")
        print("  cd forkmark && uvicorn backend.main:app --reload\n")
        sys.exit(1)

    # Auto-bootstrap an API key if none was provided via environment
    if "X-API-Key" not in HEADERS:
        print("[check] No FORKMARK_API_KEY set — bootstrapping one...")
        try:
            kr = httpx.post(
                BASE_URL + "/api/keys",
                json={"name": "demo-seeder"},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            kr.raise_for_status()
            raw_key = kr.json().get("raw_key", "")
            if raw_key:
                HEADERS["X-API-Key"] = raw_key
                print(f"[check] ✓ API key created: {raw_key[:12]}...\n")
            else:
                print("[error] Could not bootstrap API key (no raw_key in response)")
                print("  Set FORKMARK_API_KEY or create a key via the UI.")
                sys.exit(1)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                print("[error] API keys already exist. Provide one via FORKMARK_API_KEY env var.")
                print("  Or run via: python run_all_demos.py (which bootstraps a shared key)")
                sys.exit(1)
            raise
        except Exception as e:
            print(f"[error] Could not bootstrap API key: {e}")
            print("  Set FORKMARK_API_KEY env var or create a key manually.")
            sys.exit(1)


def seed():
    check_backend()

    print("═" * 65)
    print("  FORKMARK HR DEMO SEEDER")
    print("  Job Description Generator — 10 Roles × 4 Steps")
    print("═" * 65 + "\n")

    print("[1/4] Creating workflow...")
    wf = api("post", "/api/workflows", {
        "name": "job-description-generator",
        "description": "4-step job description pipeline: role overview, key responsibilities, required qualifications, benefits and culture.",
    })
    if not wf:
        wfs = api("get", "/api/workflows")
        wf  = next((w for w in (wfs or []) if w["name"] == "job-description-generator"), None)
    if not wf:
        print("[error] Could not create or find workflow.")
        sys.exit(1)
    print(f"       workflow id: {wf['id']}\n")

    print("[2/4] Creating eval run...")
    er = api("post", "/api/eval-runs", {
        "workflow_name": "job-description-generator",
        "name": "Inclusive Role-Specific Prompt v2 vs Generic Template v1 — JD Generation",
        "description": "Evaluating whether a role-specific prompt with inclusion guidance produces significantly better job descriptions than a generic template across 10 roles and functions.",
        "branch_a_config": {"label": "Inclusive Role-Specific Prompt v2 (Baseline)", "model_id": "gpt-4o", "temperature": 0.4},
        "branch_b_config": {"label": "Generic Template v1 (Challenger)", "model_id": "gpt-4o", "temperature": 0.4},
        "total_cases": len(CASES),
    })
    if not er:
        print("[error] Could not create eval run.")
        sys.exit(1)
    er_id = er["id"]
    print(f"       eval run id: {er_id}\n")

    print(f"[3/4] Seeding {len(CASES)} test cases (4 steps each)...")
    print()

    for i, c in enumerate(CASES):
        print(f"  [{i+1:02d}/{len(CASES)}] {c['label']}")

        run = api("post", "/api/sdk/runs", {
            "workflow_name":   "job-description-generator",
            "input_data":      {"brief": c["brief"], "label": c["label"]},
            "eval_run_id":     er_id,
            "test_case_label": c["label"],
        })
        if not run:
            print("         [skip] run creation failed")
            continue

        ba = api("post", "/api/sdk/branches", {
            "run_id": run["id"], "name": "inclusive-role-specific-v2", "model_id": "gpt-4o",
            "temperature": 0.4, "is_baseline": True,
        })
        bb = api("post", "/api/sdk/branches", {
            "run_id": run["id"], "name": "generic-template-v1", "model_id": "gpt-4o",
            "temperature": 0.4, "is_baseline": False,
        })
        if not ba or not bb:
            print("         [skip] branch creation failed")
            continue

        steps = [
            ("role_overview",           c["ro_a"], c["ro_b"]),
            ("key_responsibilities",     c["kr_a"], c["kr_b"]),
            ("required_qualifications",  c["rq_a"], c["rq_b"]),
            ("benefits_culture",         c["bc_a"], c["bc_b"]),
        ]
        msg = [{"role": "user", "content": c["brief"]}]
        for idx, (step, out_a, out_b) in enumerate(steps):
            base_in = 50 + len(c["brief"]) // 4
            api("post", "/api/sdk/steps", {
                "run_id": run["id"], "branch_id": ba["id"],
                "step_name": step, "step_index": idx,
                "input_messages": msg, "output_text": out_a,
                "model_id": "gpt-4o", "temperature": 0.4,
                "tokens_input": base_in, "tokens_output": len(out_a.split()),
                "latency_ms": 350 + idx * 55,
            })
            api("post", "/api/sdk/steps", {
                "run_id": run["id"], "branch_id": bb["id"],
                "step_name": step, "step_index": idx,
                "input_messages": msg, "output_text": out_b,
                "model_id": "gpt-4o", "temperature": 0.4,
                "tokens_input": base_in, "tokens_output": len(out_b.split()),
                "latency_ms": 220 + idx * 40,
            })

        api("post", f"/api/sdk/runs/{run['id']}/complete", {"status": "completed"})
        comp = api("post", "/api/sdk/comparisons", {
            "run_id": run["id"],
            "branch_a_id": ba["id"],
            "branch_b_id": bb["id"],
            "eval_run_id": er_id,
            "test_case_label": c["label"],
        })
        if comp:
            d = comp.get("divergence_score", 0) or 0
            bar = "█" * int(d * 20) + "░" * (20 - int(d * 20))
            emoji = "🟢" if d < 0.2 else "🟡" if d < 0.5 else "🔴"
            print(f"         {emoji} divergence: {bar}  {d:.0%}")

    print()
    print("[4/4] Completing eval run...")
    api("patch", f"/api/eval-runs/{er_id}/complete", {
        "status": "completed", "total_cases": len(CASES),
    })

    print()
    print("═" * 65)
    print("  HR DEMO READY")
    print("═" * 65)
    print()
    print("  Open Forkmark:  http://localhost:5173")
    print(f"  Eval Run ID:     {er_id}")
    print()
    print("  High-divergence cases to review:")
    print("  • senior-software-engineer — specific salary, equity, visa sponsorship vs bullets")
    print("  • sales-director           — deal sizes, quota, accelerators vs generic")
    print("  • devops-engineer          — healthcare compliance context vs boilerplate")
    print("  • finance-analyst          — PE transformation context vs template")
    print()


if __name__ == "__main__":
    seed()
