import { useEffect, useState } from 'react'

interface CountdownProps {
  seconds: number
  isActive: boolean
  onComplete: () => void
}

const Countdown = ({ seconds, isActive, onComplete }: CountdownProps) => {
  const [remaining, setRemaining] = useState(seconds)

  useEffect(() => {
    setRemaining(seconds)
  }, [seconds])

  useEffect(() => {
    if (!isActive) {
      return
    }

    const interval = setInterval(() => {
      setRemaining((prev) => (prev > 0 ? prev - 1 : 0))
    }, 1000)

    return () => clearInterval(interval)
  }, [isActive])

  useEffect(() => {
    if (isActive && remaining === 0) {
      onComplete()
    }
  }, [isActive, remaining, onComplete])

  const minutes = Math.floor(remaining / 60)
  const secs = remaining % 60
  const paddedSeconds = secs.toString().padStart(2, '0')

  return (
    <div className="countdown">
      <div className="time">
        {minutes}:{paddedSeconds}
      </div>
      <p>{isActive ? '番茄鐘進行中' : '準備開始你的番茄鐘'}</p>
    </div>
  )
}

export default Countdown
