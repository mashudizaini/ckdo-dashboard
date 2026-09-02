import React from 'react';
import { ChevronDown } from 'lucide-react';
import { useEMagazineStore } from '../../stores/emagazineStore';

export default function TableOfContents() {
  const { tableOfContents, currentPage, setCurrentPage } = useEMagazineStore();
  const [expandedSections, setExpandedSections] = React.useState({});

  const toggleSection = (section) => {
    setExpandedSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  return (
    <div className="bg-white border-r border-gray-200 overflow-y-auto">
      <div className="p-4">
        <h2 className="text-lg font-bold mb-4">Contents</h2>

        <div className="space-y-2">
          {Object.entries(tableOfContents).map(([section, items]) => (
            <div key={section}>
              <button
                onClick={() => toggleSection(section)}
                className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-100 rounded transition group"
              >
                <ChevronDown
                  size={16}
                  className={`transition ${
                    expandedSections[section] ? 'rotate-0' : '-rotate-90'
                  }`}
                />
                <span className="text-sm font-semibold text-gray-700 group-hover:text-gray-900">
                  {section}
                </span>
                <span className="ml-auto text-xs text-gray-500">
                  {items.length}
                </span>
              </button>

              {expandedSections[section] && (
                <div className="ml-2 space-y-1 mt-2">
                  {items.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => setCurrentPage(item.page)}
                      className={`w-full text-left px-3 py-2 text-xs rounded transition ${
                        currentPage === item.page
                          ? 'bg-blue-100 text-blue-700 font-semibold'
                          : 'text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="truncate flex-1">{item.title}</span>
                        <span className="ml-2 text-gray-400 text-xs">
                          p{item.page}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
