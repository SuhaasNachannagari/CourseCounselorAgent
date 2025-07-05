import React, { useState, useEffect, useRef } from 'react';
import { Bot, User, Send } from 'lucide-react';

// A simple component for a single chat message
const ChatMessage = ({ role, content }) => {
  const isBot = role === 'assistant';
  // Splits text by **bold** markdown to apply styling
  const messageParts = content.split(/(\*\*.*?\*\*)/g); 

  return (
    <div className={`flex items-start gap-3 my-4 ${isBot ? 'justify-start' : 'justify-end'}`}>
      {isBot && (
        <div className="w-10 h-10 rounded-full bg-amber-500 flex-shrink-0 flex items-center justify-center text-white">
          <Bot size={24} />
        </div>
      )}
      <div className={`p-4 max-w-2xl rounded-xl shadow-md ${isBot ? 'bg-white text-gray-800' : 'bg-indigo-600 text-white'}`}>
        <p className="whitespace-pre-wrap">
          {messageParts.map((part, index) =>
            part.startsWith('**') && part.endsWith('**') ? (
              <strong key={index}>{part.slice(2, -2)}</strong>
            ) : (
              part
            )
          )}
        </p>
      </div>
      {!isBot && (
        <div className="w-10 h-10 rounded-full bg-gray-200 flex-shrink-0 flex items-center justify-center text-gray-600">
          <User size={24} />
        </div>
      )}
    </div>
  );
};

// Main App Component
export default function App() {
  const [chatHistory, setChatHistory] = useState([
    {
      role: 'assistant',
      content: "Hello! I'm the Purdue Course Advisor. Ask me to compare professors or find out about a course's difficulty.",
    },
  ]);
  const [userInput, setUserInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const chatEndRef = useRef(null);
  
  // The URL of your Python backend. Ensure this matches where your FastAPI server is running.
  const API_URL = "http://localhost:8000/agent/invoke";

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, isLoading]);

  const handleSendMessage = async () => {
    if (!userInput.trim() || isLoading) return;

    const newUserMessage = { role: 'user', content: userInput };
    // Add the user's message to the history immediately for a responsive feel
    const currentChatHistory = [...chatHistory, newUserMessage];
    setChatHistory(currentChatHistory);
    setUserInput('');
    setIsLoading(true);

    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // Send the chat history (excluding the initial welcome message) to the backend
        body: JSON.stringify({ chat_history: currentChatHistory.slice(1) }),
      });

      if (!response.ok) {
        throw new Error(`API call failed with status: ${response.status}`);
      }

      const result = await response.json();
      const botResponse = { role: 'assistant', content: result.response };
      setChatHistory(prev => [...prev, botResponse]);

    } catch (error) {
      console.error('Error fetching from agent API:', error);
      const errorMessage = {
        role: 'assistant',
        content: `Sorry, an error occurred: ${error.message}. Please make sure the backend server is running.`,
      };
      setChatHistory(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="font-sans bg-gray-100 h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200 p-4 shadow-sm flex justify-center items-center gap-3">
        <img src="[https://upload.wikimedia.org/wikipedia/commons/thumb/3/35/Purdue_Boilermakers_logo.svg/1200px-Purdue_Boilermakers_logo.svg.png](https://upload.wikimedia.org/wikipedia/commons/thumb/3/35/Purdue_Boilermakers_logo.svg/1200px-Purdue_Boilermakers_logo.svg.png)" alt="Purdue Logo" className="h-8 w-8" />
        <h1 className="text-xl font-bold text-gray-800 text-center">Purdue Course Advisor</h1>
      </header>

      <main className="flex-1 overflow-y-auto p-4 md:p-6">
        <div className="max-w-4xl mx-auto">
          {chatHistory.map((msg, index) => (
            <ChatMessage key={index} role={msg.role} content={msg.content} />
          ))}
          {isLoading && (
            <div className="flex items-start gap-3 my-4 justify-start">
              <div className="w-10 h-10 rounded-full bg-amber-500 flex-shrink-0 flex items-center justify-center text-white"><Bot size={24} /></div>
              <div className="p-4 max-w-xl rounded-xl shadow-md bg-white">
                <div className="flex items-center gap-2 text-gray-600">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-75"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-150"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-300"></div>
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
      </main>

      <footer className="bg-white border-t border-gray-200 p-4">
        <div className="max-w-4xl mx-auto">
          <div className="relative">
            <textarea
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="e.g., Is CS 182 easier with Sellke or Adams?"
              className="w-full p-4 pr-16 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none"
              rows={1}
              disabled={isLoading}
              style={{ minHeight: '52px' }}
            />
            <button
              onClick={handleSendMessage}
              disabled={isLoading || !userInput.trim()}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-2 rounded-full bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300 disabled:cursor-not-allowed transition-colors"
            >
              <Send size={20} />
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
