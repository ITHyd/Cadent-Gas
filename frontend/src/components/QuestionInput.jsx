import { useState } from 'react';

const QuestionInput = ({ questionData, onSubmit }) => {
  const [answer, setAnswer] = useState('');
  const questionType = questionData?.question_type;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (answer || !questionData?.required) {
      onSubmit({ [questionData.question_text]: answer });
      setAnswer('');
    }
  };

  const handleOptionClick = (option) => {
    onSubmit({ [questionData.question_text]: option });
  };

  return (
    <div className="space-y-4">
      {questionType === 'yes_no' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <button
            onClick={() => handleOptionClick('Yes')}
            className="btn-base w-full bg-emerald-600 text-white hover:bg-emerald-700"
          >
            Yes
          </button>
          <button
            onClick={() => handleOptionClick('No')}
            className="btn-base w-full bg-red-600 text-white hover:bg-red-700"
          >
            No
          </button>
        </div>
      )}

      {questionType === 'multiple_choice' && questionData.options && (
        <div className="grid gap-3 sm:grid-cols-2">
          {questionData.options.map((option) => {
            const label = typeof option === 'object' && option !== null && option.label
              ? option.label
              : option;
            return (
              <button
                key={label}
                onClick={() => handleOptionClick(label)}
                className="rounded-xl border-2 border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition-colors hover:border-brand-500 hover:bg-brand-50"
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      {(questionType === 'text' || questionType === 'number') && (
        <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
          <input
            type={questionType === 'number' ? 'number' : 'text'}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            required={questionData.required}
            placeholder="Type your answer..."
            className="input-control flex-1"
          />
          <button type="submit" className="btn-primary">
            Send
          </button>
        </form>
      )}
    </div>
  );
};

export default QuestionInput;
