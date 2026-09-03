const NAV_ITEMS = [
  { key: 'TIME', label: 'TIME' },
  { key: 'TRADE', label: 'TRADE' },
  { key: 'INSTRUMENT', label: 'INSTRUMENT' },
  { key: 'SOURCE', label: 'SOURCE' },
  { key: 'BEHAVIOR', label: 'BEHAVIOR' },
  { key: 'OUTCOMES', label: 'OUTCOMES' },
  { key: 'MARKET', label: 'MARKET' },
  { key: 'STRATEGY', label: 'STRATEGY' },
  { key: 'EXECUTION', label: 'EXECUTION' },
  { key: 'RISK', label: 'RISK' },
];

interface Props {
  activeSection?: string;
  onNavigate: (sectionKey: string) => void;
}

export function QuickNav({ activeSection, onNavigate }: Props) {
  return (
    <nav className="graphs-quick-nav" aria-label="Report sections">
      {NAV_ITEMS.map((item) => (
        <button
          key={item.key}
          type="button"
          className={activeSection === item.key ? 'active' : undefined}
          onClick={() => onNavigate(item.key)}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}

export { NAV_ITEMS };
