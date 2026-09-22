import React from 'react';

export function Tabs({ value, onValueChange, children }) {
  return (
    <div className="w-full">
      {React.Children.map(children, (child) => {
        if (child.type === TabsList || child.type === TabsContent) {
          return React.cloneElement(child, { value, onValueChange });
        }
        return child;
      })}
    </div>
  );
}

export function TabsList({ children, value, onValueChange, ...props }) {
  return (
    <div {...props} className="flex border-b border-gray-200 bg-gray-50">
      {React.Children.map(children, (child) => {
        if (child.type === TabsTrigger) {
          return React.cloneElement(child, { value, onValueChange });
        }
        return child;
      })}
    </div>
  );
}

export function TabsTrigger({ children, value, onValueChange, ...props }) {
  const isActive = value === props.value;

  return (
    <button
      {...props}
      onClick={() => onValueChange(props.value)}
      className={`px-6 py-3 font-medium transition border-b-2 ${
        isActive
          ? 'border-blue-600 text-blue-600'
          : 'border-transparent text-gray-600 hover:text-gray-900'
      }`}
    >
      {children}
    </button>
  );
}

export function TabsContent({ children, value, ...props }) {
  if (value !== props.value) {
    return null;
  }

  return <div {...props}>{children}</div>;
}
