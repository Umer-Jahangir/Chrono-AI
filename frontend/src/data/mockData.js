// Data for the Search Page
export const searchResults = [
  {
    id: 1,
    title: "FYP_Final_Report.pdf",
    type: "PDF",
    source: "WhatsApp",
    date: "2 Aug 2026, 10:30 AM",
    sender: "Ahmed Raza",
    size: "4.2 MB",
    score: 92,
    preview: "This file contains the final report of our FYP project with all modules and implementation details...",
    summary: "This is the final report of the FYP project. It includes system overview, methodology, implementation, results, and conclusion.",
    iconClass: "fa-solid fa-file-pdf",
    iconColor: "text-red-600",
    iconBg: "bg-red-100",
    matchReasons: [
      "Received between 1 Aug - 5 Aug",
      "Contains keywords: project, report, implementation",
      "High semantic similarity with your query"
    ]
  },
  {
    id: 2,
    title: "Project_Document.pdf",
    type: "PDF",
    source: "WhatsApp",
    date: "4 Aug 2026, 03:15 PM",
    sender: "Ali Hamza",
    size: "3.8 MB",
    score: 76,
    preview: "Project documentation and requirements with features list and system architecture...",
    summary: "Comprehensive requirements documentation and architectural specs.",
    iconClass: "fa-solid fa-file-pdf",
    iconColor: "text-red-600",
    iconBg: "bg-red-100",
    matchReasons: ["Matches keywords: project, architecture"]
  },
  {
    id: 3,
    title: "Project_Requirements.docx",
    type: "DOCX",
    source: "WhatsApp",
    date: "1 Aug 2026, 09:45 AM",
    sender: "Sara Khan",
    size: "1.2 MB",
    score: 58,
    preview: "Initial requirements and features discussed for the project...",
    summary: "Early stage feature drafts and stakeholder requirements.",
    iconClass: "fa-solid fa-file-word",
    iconColor: "text-blue-600",
    iconBg: "bg-blue-100",
    matchReasons: ["Date range match", "Sender match"]
  }
];

// Data for Dashboard Connections
export const dashboardConnections = [
  {
    id: "drive",
    name: "Google Drive",
    status: "Active",
    statusColor: "text-primary",
    statusBg: "bg-primary/10",
    icon: "folder_data",
    iconColor: "text-primary",
    desc: "Last synced 2m ago",
    progress: 100
  },
  {
    id: "slack",
    name: "Slack Workspace",
    status: "Syncing...",
    statusColor: "text-secondary",
    statusBg: "bg-secondary/10",
    icon: "forum",
    iconColor: "text-secondary",
    desc: "Indexing messages (45%)",
    progress: 45
  },
  {
    id: "notion",
    name: "Notion Space",
    status: "Syncing...",
    statusColor: "text-tertiary",
    statusBg: "bg-tertiary/10",
    icon: "description",
    iconColor: "text-tertiary",
    desc: "Processing pages (82%)",
    progress: 82
  }
];