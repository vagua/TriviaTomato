import { useState } from 'react'
import Countdown from '../components/Countdown'
import QuizModal from '../components/QuizModal'
import { fetchQuiz, startSession, type QuizQuestion } from '../api/client'

// Allow short sprints; 0.5 分鐘 = 30 秒
const DEFAULT_MINUTES = 0.5

const TimerPage = () => {
  const [activity, setActivity] = useState('')
  const [minutes, setMinutes] = useState(DEFAULT_MINUTES)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [countdownSeed, setCountdownSeed] = useState(0)
  const [isCounting, setIsCounting] = useState(false)
  const [questions, setQuestions] = useState<QuizQuestion[]>([])
  const [showModal, setShowModal] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isLoadingQuiz, setIsLoadingQuiz] = useState(false)

  const sanitizedMinutes = minutes > 0 ? minutes : DEFAULT_MINUTES
  const durationSeconds = Math.max(0.5, sanitizedMinutes) * 60

  const handleStart = async () => {
    if (!activity.trim()) {
      setError('請輸入活動內容')
      return
    }

    try {
      setError(null)
      const { session_id } = await startSession(activity.trim())
      setSessionId(session_id)
      setQuestions([])
      setShowModal(false)
      setIsCounting(true)
      setCountdownSeed((seed) => seed + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法啟動番茄鐘')
    }
  }

  const handleCountdownComplete = async () => {
    if (!sessionId) {
      return
    }
    setIsLoadingQuiz(true)
    setIsCounting(false)
    try {
      const maxAttempts = 3
      let lastErr: unknown = null
      for (let i = 0; i < maxAttempts; i++) {
        try {
          const quiz = await fetchQuiz(sessionId)
          setQuestions(quiz.questions || [])
          setShowModal(true)
          lastErr = null
          break
        } catch (err) {
          lastErr = err
          await new Promise((resolve) => setTimeout(resolve, 1000))
        }
      }
      if (lastErr) {
        throw lastErr
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '取得測驗失敗')
    } finally {
      setIsLoadingQuiz(false)
    }
  }

  return (
    <div className="page">
      <header>
        <h1>靈感番茄 Pomodoro + Quiz</h1>
        <p>輸入專注主題，等待 AI 幫你準備專屬問答</p>
      </header>

      <section className="panel">
        <label>
          活動內容
          <input
            type="text"
            value={activity}
            onChange={(e) => setActivity(e.target.value)}
            placeholder="例如：學習 k3s 架構"
          />
        </label>

        <label>
          番茄鐘時間（分鐘）
          <input
            type="number"
            min={0.5}
            step={0.5}
            value={minutes}
            onChange={(e) => {
              const value = Number(e.target.value)
              setMinutes(Number.isNaN(value) ? DEFAULT_MINUTES : value)
            }}
          />
        </label>

        <button onClick={handleStart} disabled={isCounting || !activity.trim()}>
          {isCounting ? '進行中…' : '開始番茄鐘'}
        </button>

        {error && <p className="error">{error}</p>}
      </section>

      <section className="timer-section">
        <Countdown
          key={countdownSeed}
          seconds={durationSeconds}
          isActive={isCounting}
          onComplete={handleCountdownComplete}
        />
        {isLoadingQuiz && <p>AI 問題生成中…</p>}
      </section>

      <QuizModal
        visible={showModal}
        questions={questions}
        onClose={() => setShowModal(false)}
      />
    </div>
  )
}

export default TimerPage
