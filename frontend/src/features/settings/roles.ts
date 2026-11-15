export const EFFORTS = ["low", "medium", "high", "xhigh", "max"];

/** What each agent does, in the words of the person reading the settings. */
export const ROLE_INFO: Record<string, { name: string; does: string }> = {
  classifier: { name: "Domain classifier", does: "Picks which domain your input belongs to." },
  planner: { name: "Outline planner", does: "Proposes the outline for a topic after a light web scan." },
  placer: { name: "Topic placer", does: "Decides which parent note a topic sits under, and which existing notes belong beside it." },
  structurer: { name: "Outline splitter", does: "Splits pasted material into an outline." },
  researcher: { name: "Researcher", does: "Researches each subtopic on the web." },
  linker: { name: "Overlap and links", does: "Spots notes that already cover something and picks related links." },
  writer: { name: "Note writer", does: "Writes the notes. Most of the cost goes here." },
  synthesizer: { name: "Overview writer", does: "Writes overview and parent notes that compare their subtopics." },
  reference_finder: { name: "Reference finder", does: "Finds and ranks credible links to cite." },
  validator: { name: "Draft checker", does: "Checks drafts for scope creep, missing depth and unsupported claims." },
  link_pruner: { name: "Link reviewer", does: "When you press “Review links” on the Notes page, keeps only the Related links a reader needs." },
  profile_builder: { name: "Profile drafter", does: "Fills in a domain profile when you press “Draft with Claude”." },
  chat_orchestrator: { name: "Chat lead", does: "Leads each chat answer: decides what to look up and writes the answer." },
  navigator: { name: "Note finder", does: "Finds the notes that could answer a question, from the map of your vault." },
  reader: { name: "Note reader", does: "Pulls the passages that matter out of the chosen notes." },
  answer_verifier: { name: "Answer checker", does: "Checks every answer against the passages it cites." },
  chat_summarizer: { name: "Chat summarizer", does: "Condenses older messages in a long chat." },
};

/** Budget settings a role exposes, stored in its `params`. */
/** `decimal` budgets accept any number above zero; the rest take whole numbers. */
export const BUDGETS: Record<string, { key: string; label: string; hint: string; decimal?: boolean }[]> = {
  researcher: [
    { key: "max_searches", label: "Web searches", hint: "At most this many per subtopic." },
    { key: "max_turns", label: "Turns", hint: "About this many back-and-forths." },
    { key: "timeout_seconds", label: "Time limit (seconds)", hint: "Per subtopic." },
  ],
  planner: [{ key: "max_searches", label: "Web searches", hint: "For the light scan before outlining." }],
  chat_orchestrator: [
    { key: "max_steps", label: "Actions per answer", hint: "Then one last call that must answer or ask." },
    { key: "max_verify_rounds", label: "Re-check rounds", hint: "A draft that still fails shows its flags." },
    { key: "budget_usd", label: "Spending cap per answer ($)", hint: "The answer wraps up once this is spent.", decimal: true },
  ],
  navigator: [{ key: "max_steps", label: "Steps per task", hint: "Lookups before it must finish." }],
  reader: [{ key: "max_steps", label: "Steps per task", hint: "Lookups before it must finish." }],
};

