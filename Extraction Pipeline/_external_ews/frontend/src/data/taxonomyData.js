export const TAXONOMY = [
  {
    id: "company_info",
    category: "Company Information",
    subcategories: [
      { name: "Company Profile", entity_type: "direct_mapping", description: "Basic company details, registration, and background." },
      { name: "Business Overview", entity_type: "direct_mapping", description: "Core business activities and operations summary." },
      { name: "Products & Services", entity_type: "direct_mapping", description: "Key products, brand portfolio, and services offered." },
      { name: "Subsidiaries & Group Structure", entity_type: "table", description: "List of subsidiaries, joint ventures, and associates." }
    ]
  },
  {
    id: "management_governance",
    category: "Management & Governance",
    subcategories: [
      { name: "Board of Directors", entity_type: "table", description: "Composition of board members, executive vs non-executive directors." },
      { name: "Key Management Personnel", entity_type: "direct_mapping", description: "CEO, CFO, Company Secretary, and key officers." },
      { name: "Corporate Governance", entity_type: "direct_mapping", description: "Governance report, compliance, and policies." },
      { name: "Board Committees", entity_type: "table", description: "Audit Committee, Nomination & Remuneration Committee, etc." }
    ]
  },
  {
    id: "shareholding_info",
    category: "Shareholding Information",
    subcategories: [
      { name: "Share Capital", entity_type: "direct_mapping", description: "Authorized, issued, and paid-up capital." },
      { name: "Shareholding Pattern", entity_type: "table", description: "Promoter vs Public shareholding distribution." },
      { name: "Major Shareholders", entity_type: "table", description: "Shareholders holding more than 1% or key institutional investors." },
      { name: "Dividend Information", entity_type: "direct_mapping", description: "Dividend per share, payout policy, and total dividend." }
    ]
  },
  {
    id: "mda",
    category: "Management Discussion & Analysis",
    subcategories: [
      { name: "Industry Overview", entity_type: "direct_mapping", description: "Macroeconomic environment and industry trends." },
      { name: "Business Review", entity_type: "direct_mapping", description: "Management analysis of operational performance." },
      { name: "Opportunities & Challenges", entity_type: "direct_mapping", description: "Key growth drivers, risks, and market challenges." },
      { name: "Future Outlook", entity_type: "direct_mapping", description: "Strategic priorities and forward-looking expectations." }
    ]
  },
  {
    id: "financial_statements",
    category: "Financial Statements",
    subcategories: [
      { name: "Balance Sheet", entity_type: "table", description: "Statement of Financial Position (Standalone & Consolidated)." },
      { name: "Profit & Loss Statement", entity_type: "table", description: "Statement of Profit and Loss / Income Statement." },
      { name: "Cash Flow Statement", entity_type: "table", description: "Operating, investing, and financing cash flows." },
      { name: "Statement of Changes in Equity", entity_type: "table", description: "Equity movement, reserves, and retained earnings." },
      { name: "Notes to Accounts", entity_type: "direct_mapping", description: "Detailed explanatory notes accompanying financial statements." },
      { name: "Accounting Policies", entity_type: "direct_mapping", description: "Significant accounting policies and Ind AS compliance." },
      { name: "Related Party Transactions", entity_type: "table", description: "Transactions with key management, subsidiaries, and group entities." },
      { name: "Contingent Liabilities", entity_type: "direct_mapping", description: "Guarantees, pending claims, and unacknowledged debts." },
      { name: "Segment Information", entity_type: "table", description: "Segment revenue, segment profit, and geographic breakdown." }
    ]
  },
  {
    id: "financial_analysis",
    category: "Financial Analysis",
    subcategories: [
      { name: "Financial Ratios", entity_type: "table", description: "Key ratios (ROE, ROCE, Debt/Equity, Current Ratio, Net Margin)." },
      { name: "Working Capital Analysis", entity_type: "direct_mapping", description: "Receivables, payables, inventory days, and working capital cycle." },
      { name: "Debt Analysis", entity_type: "direct_mapping", description: "Borrowings breakdown, interest coverage, and repayment terms." }
    ]
  },
  {
    id: "business_performance",
    category: "Business Performance",
    subcategories: [
      { name: "Revenue & Sales Performance", entity_type: "direct_mapping", description: "Revenue growth, product-wise sales, and volume trends." },
      { name: "Segment Performance", entity_type: "table", description: "Business unit performance and segment margins." },
      { name: "Operational Performance", entity_type: "direct_mapping", description: "Plant capacity utilization, production output, and efficiency." },
      { name: "Key Performance Indicators (KPIs)", entity_type: "table", description: "Operational and financial KPIs." }
    ]
  },
  {
    id: "risk_management",
    category: "Risk Management",
    subcategories: [
      { name: "Business Risks", entity_type: "direct_mapping", description: "Commercial, competitive, and market demand risks." },
      { name: "Financial Risks", entity_type: "direct_mapping", description: "Foreign exchange, liquidity, interest rate, and credit risks." },
      { name: "Operational Risks", entity_type: "direct_mapping", description: "Supply chain, technology, and facility operational risks." },
      { name: "Regulatory Risks", entity_type: "direct_mapping", description: "Legal compliance, policy shifts, and environmental regulations." }
    ]
  },
  {
    id: "human_resources",
    category: "Human Resources",
    subcategories: [
      { name: "Workforce Information", entity_type: "direct_mapping", description: "Total headcounts, permanent vs contract employees." },
      { name: "Training & Development", entity_type: "direct_mapping", description: "Employee skill programs, training hours, and talent development." },
      { name: "Employee Welfare", entity_type: "direct_mapping", description: "Health benefits, safety metrics, and workplace well-being." },
      { name: "Diversity & Inclusion", entity_type: "direct_mapping", description: "Gender ratio, female board/workforce representation." }
    ]
  },
  {
    id: "esg_sustainability",
    category: "ESG & Sustainability",
    subcategories: [
      { name: "Environmental", entity_type: "direct_mapping", description: "Energy consumption, carbon emissions, water & waste metrics." },
      { name: "Social", entity_type: "direct_mapping", description: "Community engagement, human rights, and safety compliance." },
      { name: "Governance", entity_type: "direct_mapping", description: "Ethics, anti-corruption policies, and whistleblower mechanisms." },
      { name: "Sustainability Initiatives", entity_type: "direct_mapping", description: "BRSR reporting, renewable energy adoption, and ESG targets." }
    ]
  },
  {
    id: "csr",
    category: "CSR (Corporate Social Responsibility)",
    subcategories: [
      { name: "CSR Spending", entity_type: "direct_mapping", description: "Mandated 2% budget, actual spend, and unspent amounts." },
      { name: "CSR Projects", entity_type: "table", description: "Key projects in education, healthcare, and rural development." },
      { name: "Community Development", entity_type: "direct_mapping", description: "Impact assessment and local community programs." }
    ]
  },
  {
    id: "legal_compliance",
    category: "Legal & Compliance",
    subcategories: [
      { name: "Litigations", entity_type: "direct_mapping", description: "Material tax disputes, legal cases, and arbitration." },
      { name: "Regulatory Compliance", entity_type: "direct_mapping", description: "SEBI, MCA, and industry-specific compliance certificates." },
      { name: "Statutory Compliance", entity_type: "direct_mapping", description: "PF, ESI, GST, and statutory dues status." }
    ]
  },
  {
    id: "strategic_initiatives",
    category: "Strategic Initiatives",
    subcategories: [
      { name: "Growth Strategy", entity_type: "direct_mapping", description: "Long-term corporate vision and strategic pillars." },
      { name: "Expansion Plans", entity_type: "direct_mapping", description: "CAPEX, new factory setup, and market entry plans." },
      { name: "Mergers & Acquisitions", entity_type: "direct_mapping", description: "M&A deals, joint ventures, and strategic investments." },
      { name: "Digital Transformation", entity_type: "direct_mapping", description: "IT infrastructure, AI/automation, and cloud initiatives." }
    ]
  },
  {
    id: "investor_info",
    category: "Investor Information",
    subcategories: [
      { name: "Share Price Performance", entity_type: "direct_mapping", description: "High/Low stock price trend during the financial year." },
      { name: "Market Capitalization", entity_type: "direct_mapping", description: "Market cap classification and valuation metrics." },
      { name: "Shareholder Information", entity_type: "direct_mapping", description: "AGM details, registrar info, and investor contacts." },
      { name: "Investor Relations", entity_type: "direct_mapping", description: "Earnings calls, investor presentations, and analyst meets." }
    ]
  },
  {
    id: "audit_info",
    category: "Audit Information",
    subcategories: [
      { name: "Auditor's Report", entity_type: "direct_mapping", description: "Statutory auditor opinion (Unmodified / Qualified)." },
      { name: "Key Audit Matters", entity_type: "direct_mapping", description: "KAMs highlighted in auditor's report." },
      { name: "Internal Controls", entity_type: "direct_mapping", description: "Evaluation of Internal Financial Controls (IFCoR)." }
    ]
  },
  {
    id: "outlook_guidance",
    category: "Outlook & Guidance",
    subcategories: [
      { name: "Management Guidance", entity_type: "direct_mapping", description: "Forward guidance on revenue and margins." },
      { name: "Growth Targets", entity_type: "direct_mapping", description: "Medium-term growth and operational targets." },
      { name: "Future Plans", entity_type: "direct_mapping", description: "R&D pipeline, product launches, and strategic goals." }
    ]
  }
];
