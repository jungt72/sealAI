'use client'

import React, { FormEvent, useState } from 'react'

export interface ChatInputProps {
  onSend: (message: string) => void
}

export default function ChatInput({ onSend }: ChatInputProps) {
  const [value, setValue] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const text = value.trim()
    if (!text) return
    onSend(text)
    setValue('')
  }

  return (
    <form onSubmit={handleSubmit} className="flex mt-4">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Deine Frage …"
        className="flex-1 border border-gray-300 rounded-l px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <button
        type="submit"
        className="bg-blue-600 text-white px-4 py-2 rounded-r hover:bg-blue-700 transition"
      >
        →
      </button>
    </form>
  )
}
