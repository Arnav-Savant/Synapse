export const EFFORTS = ["low", "medium", "high", "xhigh", "max"];

/** What each agent does, in the words of the person reading the settings. */
export const ROLE_INFO: Record<string, { name: string; does: string }> = {
  classifier: { name: "Domain classifier", does: "Picks which domain your input belongs to." },
  planner: { name: "Outline planner", does: "Proposes the outline for a topic after a light web scan." },
  placer: { name: "Topic placer", does: "Decides which hub a topic sits under, and which existing notes belong beside it." },
  structurer: { name: "Outline splitter", does: "Splits pasted material into an outline." },
  researcher: { name: "Researcher", does: "Researches each subtopic on the web." },
  linker: { name: "Overlap and links", does: "Spots notes that already cover something and picks related links." },
  writer: { name: "Note writer", does: "Writes the notes. Most of the cost goes here." },
  synthesizer: { name: "Overview writer", does: "Writes overview and parent notes that compare their subtopics." },
  reference_finder: { name: "Reference finder", does: "Finds and ranks credible links to cite." },
  validator: { name: "Draft checker", does: "Checks drafts for scope creep, missing depth and unsupported claims." },
  profile_builder: { name: "Profile drafter", does: "Fills in a domain profile when you press “Draft with Claude”." },
};

/** Budget settings a role exposes, stored in its `params`. */
export const BUDGETS: Record<string, { key: string; label: string; hint: string }[]> = {
  researcher: [
    { key: "max_searches", label: "Web searches", hint: "At most this many per subtopic." },
    { key: "max_turns", label: "Turns", hint: "About this many back-and-forths." },
    { key: "timeout_seconds", label: "Time limit (seconds)", hint: "Per subtopic." },
  ],
  planner: [{ key: "max_searches", label: "Web searches", hint: "For the light scan before outlining." }],
};

