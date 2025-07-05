import React, { useState, useEffect, useRef } from 'react';
import './App.css'; // Make sure you have App.css for styling

// We can generate a new session ID for each page load.
const sessionId = `session_${Date.now()}`;

function App() {
  const [messages, setMessages] = useState([
    {
      text: "I'm connected to the live server. Ask me about a Purdue course!",
      sender: "bot"
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const chatWindowRef = useRef(null);

  // Automatically scroll down when messages change
  useEffect(() => {
    if (chatWindowRef.current) {
      chatWindowRef.current.scrollTop = chatWindowRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const handleSendMessage = async (event) => {
    event.preventDefault();
    const userMessage = input.trim();
    if (!userMessage) return;

    setMessages(prev => [...prev, { text: userMessage, sender: "user" }]);
    setInput('');
    setIsLoading(true);

    try {
      // Ensure this URL is exactly the one from your working curl command
      const response = await fetch("http://CourseAgentPurdue.eba-wiqu3jpu.us-west-2.elasticbeanstalk.com/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: userMessage,
          session_id: sessionId,
        }),
      });

      // Check if the response is successful
      if (!response.ok) {
        // Try to get more error info from the response body
        const errorData = await response.text();
        throw new Error(`HTTP error! Status: ${response.status} - ${errorData}`);
      }

      const data = await response.json();
      setMessages(prev => [...prev, { text: data.reply, sender: "bot" }]);

    } catch (error) {
      console.error("Fetch error:", error);
      setMessages(prev => [...prev, { text: `There was an error connecting to the agent. Please check the console. Details: ${error.message}`, sender: "bot", isError: true }]);
    } finally {
      setIsLoading(false);
    }
  };

  const formatBotMessage = (text) => {
    return text.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  };

  return (
    <div id="chat-container">
      <div id="chat-header">
        <h2>Purdue Course Advisor</h2>
        <p>Get the real story on courses and professors.</p>
      </div>
      <div id="chat-window" ref={chatWindowRef}>
        {messages.map((msg, index) => (
          <div key={index} className={`message ${msg.sender}-message ${msg.isError ? 'error' : ''}`}>
            <p dangerouslySetInnerHTML={{ __html: msg.sender === 'bot' ? formatBotMessage(msg.text) : msg.text }} />
          </div>
        ))}
        {isLoading && (
          <div className="message bot-message">
            <div className="typing-indicator"><span></span><span></span><span></span></div>
          </div>
        )}
      </div>
      <form id="chat-form" onSubmit={handleSendMessage}>
        <input
          type="text"
          id="message-input"
          placeholder="Ask about a course..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isLoading}
          autoComplete="off"
        />
        <button type="submit" disabled={isLoading || !input}>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="icon"><path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 24.1 24.1 0 0 0 18.226-10.372.75.75 0 0 0 0-.856A24.1 24.1 0 0 0 3.478 2.404Z" /></svg>
        </button>
      </form>
    </div>
  );
}

export default App;