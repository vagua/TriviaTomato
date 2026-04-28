import { useEffect, useState } from 'react'
import type { QuizQuestion } from '../api/client'

interface QuizModalProps {
  visible: boolean
  questions: QuizQuestion[]
  onClose: () => void
}

type SelectedState = Record<number, number | null>

const QuizModal = ({ visible, questions, onClose }: QuizModalProps) => {
  const [selected, setSelected] = useState<SelectedState>({})

  useEffect(() => {
    if (visible) {
      setSelected({})
    }
  }, [visible, questions])

  if (!visible) {
    return null
  }

  const handleSelect = (questionIndex: number, optionIndex: number) => {
    setSelected((prev) => ({
      ...prev,
      [questionIndex]: optionIndex,
    }))
  }

  return (
    <div className="modal-overlay">
      <div className="modal">
        <h2>AI Trivia Quiz</h2>
        {questions.length === 0 ? (
          <p>暫無題目可顯示</p>
        ) : (
          <ul className="quiz-list">
            {questions.map((question, qIndex) => {
              const chosen = selected[qIndex]
              const isAnswered = typeof chosen === 'number'
              const isCorrect = isAnswered && chosen === question.answer_index
              return (
                <li key={`${qIndex}-${question.prompt}`} className="quiz-item">
                  <p className="quiz-question">{question.prompt}</p>
                  <div className="quiz-options">
                    {question.options.map((option, optionIndex) => {
                      const isUserPick = chosen === optionIndex
                      const showCorrect =
                        isAnswered && optionIndex === question.answer_index
                      return (
                        <button
                          key={`${optionIndex}-${option}`}
                          className={`quiz-option ${
                            isUserPick ? 'selected' : ''
                          } ${showCorrect ? 'correct' : ''}`}
                          onClick={() => handleSelect(qIndex, optionIndex)}
                          disabled={isAnswered}
                        >
                          <span className="quiz-option-label">
                            {String.fromCharCode(65 + optionIndex)}.
                          </span>
                          <span>{option}</span>
                        </button>
                      )
                    })}
                  </div>
                  {isAnswered && (
                    <div
                      className={`quiz-result ${
                        isCorrect ? 'correct' : 'incorrect'
                      }`}
                    >
                      <strong>{isCorrect ? '答對了！' : '可惜答錯'}</strong>
                      <p>{question.explanation}</p>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
        <button onClick={onClose}>關閉</button>
      </div>
    </div>
  )
}

export default QuizModal
