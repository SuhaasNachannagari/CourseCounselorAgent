
import React, { useState, useRef, useEffect } from 'react';
import { Send, MessageCircle, GraduationCap, Calendar, BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface Message {
  id: number;
  text: string;
  sender: 'user' | 'bot';
  timestamp: Date;
}

const ChatInterface = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      text: "Hello! I'm your Purdue course advisor. I'm here to help you plan your academic journey, choose courses, and answer questions about your degree requirements. How can I assist you today?",
      sender: 'bot',
      timestamp: new Date()
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [sessionId] = useState(() => `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;

    const userMessage: Message = {
      id: Date.now(),
      text: inputValue,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    const currentInput = inputValue;
    setInputValue('');
    setIsTyping(true);

    try {
      const response = await fetch("https://dvk9w45cc1.execute-api.us-east-2.amazonaws.com/prod/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: currentInput,
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      const botResponse: Message = {
        id: Date.now() + 1,
        text: data.response || "I'm sorry, I couldn't process your request right now. Please try again.",
        sender: 'bot',
        timestamp: new Date()
      };
      
      setMessages(prev => [...prev, botResponse]);
    } catch (error) {
      console.error('Error calling chat API:', error);
      
      const errorResponse: Message = {
        id: Date.now() + 1,
        text: "I'm sorry, I'm having trouble connecting right now. Please try again in a moment.",
        sender: 'bot',
        timestamp: new Date()
      };
      
      setMessages(prev => [...prev, errorResponse]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleQuickAction = (action: string) => {
    setInputValue(action);
  };

  const quickActions = [
    "Help me plan my next semester",
    "What are the prerequisites for CS 180?",
    "Show me graduation requirements",
    "I need help choosing electives"
  ];

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-purdue-light-gray to-white">
      {/* Header */}
      <div className="bg-gradient-to-r from-purdue-black to-purdue-dark-gray text-white p-4 shadow-lg">
        <div className="flex items-center space-x-3">
          <div className="bg-purdue-gold p-2 rounded-full">
            <GraduationCap className="h-6 w-6 text-purdue-black" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Purdue Course Advisor</h1>
            <p className="text-sm text-gray-300">Your academic planning assistant</p>
          </div>
        </div>
      </div>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in`}
          >
            <div
              className={`max-w-xs md:max-w-md lg:max-w-lg px-4 py-3 rounded-2xl shadow-md ${
                message.sender === 'user'
                  ? 'bg-gradient-to-r from-purdue-gold to-purdue-dark-gold text-purdue-black'
                  : 'bg-white text-purdue-dark-gray border border-gray-200'
              }`}
            >
              <p className="text-sm leading-relaxed">{message.text}</p>
              <p className={`text-xs mt-2 ${
                message.sender === 'user' ? 'text-purdue-black/70' : 'text-gray-500'
              }`}>
                {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
          </div>
        ))}
        
        {/* Typing Indicator */}
        {isTyping && (
          <div className="flex justify-start animate-fade-in">
            <div className="bg-white text-purdue-dark-gray px-4 py-3 rounded-2xl shadow-md border border-gray-200">
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-purdue-gold rounded-full animate-typing"></div>
                <div className="w-2 h-2 bg-purdue-gold rounded-full animate-typing" style={{ animationDelay: '0.2s' }}></div>
                <div className="w-2 h-2 bg-purdue-gold rounded-full animate-typing" style={{ animationDelay: '0.4s' }}></div>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Quick Actions */}
      {messages.length === 1 && (
        <div className="px-4 pb-2">
          <p className="text-sm text-gray-600 mb-2">Quick actions:</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {quickActions.map((action, index) => (
              <button
                key={index}
                onClick={() => handleQuickAction(action)}
                className="text-left p-3 bg-white border border-purdue-gold/30 rounded-lg hover:bg-purdue-gold/10 transition-colors duration-200 text-sm"
              >
                <div className="flex items-center space-x-2">
                  {index === 0 && <Calendar className="h-4 w-4 text-purdue-gold" />}
                  {index === 1 && <BookOpen className="h-4 w-4 text-purdue-gold" />}
                  {index === 2 && <GraduationCap className="h-4 w-4 text-purdue-gold" />}
                  {index === 3 && <MessageCircle className="h-4 w-4 text-purdue-gold" />}
                  <span>{action}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-gray-200">
        <div className="flex space-x-2">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Ask about courses, prerequisites, scheduling..."
            className="flex-1 border-purdue-gold/30 focus:border-purdue-gold focus:ring-purdue-gold/20"
            onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
          />
          <Button
            onClick={handleSendMessage}
            disabled={!inputValue.trim() || isTyping}
            className="bg-gradient-to-r from-purdue-gold to-purdue-dark-gold hover:from-purdue-dark-gold hover:to-purdue-gold text-purdue-black font-semibold transition-all duration-200"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
