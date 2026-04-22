import React, { useState } from 'react';
import { Send } from 'lucide-react';

const OptimizedChatInput = ({ placeholder, onSubmit, isTyping, className, buttonClassName }) => {
  const [inputValue, setInputValue] = useState('');
  
  const handleAsk = () => {
    if (inputValue.trim() && !isTyping) {
      onSubmit(inputValue);
      setInputValue('');
    }
  };

  return (
    <div className="relative flex items-center w-full group pointer-events-auto shadow-2xl rounded-2xl ring-1 ring-black/5">
      <input 
        type="text"
        className={className || "w-full pl-6 pr-14 py-4 bg-gray-50 border border-gray-100 rounded-2xl text-sm focus:ring-2 focus:ring-blue-500/20 outline-none transition-all placeholder:text-gray-400 font-medium"}
        placeholder={placeholder}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
      />
      <button 
        onClick={handleAsk}
        disabled={!inputValue.trim() || isTyping}
        className={buttonClassName || "absolute right-2 p-2.5 bg-blue-600 text-white rounded-xl shadow-lg shadow-blue-500/20 hover:scale-105 active:scale-95 disabled:opacity-20 disabled:scale-100 transition-all"}
      >
        <Send size={18} />
      </button>
    </div>
  );
};

export default OptimizedChatInput;
