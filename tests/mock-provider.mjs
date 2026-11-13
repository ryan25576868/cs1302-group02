/**
 * Development-only mock OpenAI-compatible endpoint used to exercise Prism's
 * local AI proxy and the AI-enhanced guide path without spending a real key.
 */
import http from 'node:http';

const PORT = Number(process.env.MOCK_PORT || 9555);

const aiGuide = {
  summary: 'This demo AI guide walks through a small discount aggregator: it filters nothing, transforms each price, and builds a total.',
  overview: {
    paragraphs: [
      'The program prepares a short price list, then asks a helper to apply a member discount to each price. The loop is the part that repeats the decision, while the helper is the part that makes the decision.',
      'By the end, the code has built a running sum inside the variable total and printed the final number. The value of total changes after every pass; it is not recomputed from scratch at the end.'
    ],
    mentalModel: {
      title: 'A discount stamp at a checkout',
      body: 'Imagine each price arriving at a checkout counter. The helper is the stamp that marks member prices down by ten percent, and the loop is the queue of items. The total is the receipt being written line by line.'
    }
  },
  walkthrough: [
    {
      title: 'The discount rule is written once',
      body: 'The helper receives a price and a membership flag. The flag controls whether the multiplication happens, and the return sends the result straight back to the caller.',
      points: ['The true branch returns early.', 'The final return is the non-member path.'],
      lines: [1, 2, 3, 5],
      badge: 'HELPER'
    },
    {
      title: 'Two pieces of starting data appear',
      body: 'The array holds the inputs, while total starts at zero because no prices have been added yet.',
      points: ['prices contains three numbers.', 'total is the running accumulator.'],
      lines: [8, 9],
      badge: 'SETUP'
    },
    {
      title: 'The loop does the repeated work',
      body: 'Each pass binds one price and passes it to the helper. Only the returned value is added to total, so the discount logic never has to be duplicated inside the loop.',
      points: ['Pass 1 adds 10.8.', 'Pass 2 adds 7.2.', 'Pass 3 adds 22.5.'],
      lines: [11, 12],
      badge: 'LOOP'
    },
    {
      title: 'The final value is printed',
      body: 'After the loop finishes, total is passed to console.log together with a label. The sample run prints Total: 40.5.',
      lines: [15],
      badge: 'OUTPUT'
    }
  ],
  lineNotes: [
    { line: 2, note: 'This condition chooses between the member price and the regular price. Because the function returns in either path, the helper always hands back a number.' },
    { line: 8, note: 'The array is the data source for the loop. Its three values determine how many passes the program needs.' },
    { line: 12, note: 'This compound assignment combines the previous total with the helper result. Each pass adds to the old value rather than replacing it.' },
    { line: 15, note: 'The console receives two arguments. The first is a label and the second is the finished total, so the final line of output tells the whole story.' }
  ],
  concepts: [
    {
      term: 'Helper function',
      definition: 'A named function that packages a rule so it can be used from more than one place.',
      inThisCode: 'applyDiscount is the rule; the loop is the place that repeats it.',
      line: 1
    },
    {
      term: 'Early return',
      definition: 'A return inside a condition can stop a function before its final line.',
      inThisCode: 'The member path returns before the second return is reached.',
      line: 3
    }
  ],
  watchOuts: [
    {
      title: 'The demo values are not universal',
      body: 'The trace uses three prices and a true membership flag. Other input values could take the other return path or change the number of loop passes.'
    }
  ],
  quiz: [
    {
      question: 'Which function turns a raw price into a discounted price?',
      answer: 'applyDiscount. It receives the price and the membership flag and returns either the discounted or original price.'
    }
  ]
};

const server = http.createServer(async (req, res) => {
  if (req.method !== 'POST') {
    res.writeHead(404).end('Not found');
    return;
  }
  let body = '';
  for await (const chunk of req) body += chunk;
  let parsed = {};
  try { parsed = JSON.parse(body); } catch { /* keep empty */ }

  const messages = Array.isArray(parsed.messages) ? parsed.messages : [];
  const lastText = messages.map((message) => String(message.content ?? '')).join('\n');
  const isConnectionTest = lastText.includes('Reply with exactly PRISM_OK') || lastText.includes('connectivity check');
  const delay = isConnectionTest ? 150 : 550;
  console.log(`[mock-ai] ${isConnectionTest ? 'test' : 'enhance'} request · model=${parsed.model} · messages=${messages.length} · prompt=${body.length} bytes · auth=${req.headers.authorization ? 'present' : 'none'}`);

  await new Promise((resolve) => setTimeout(resolve, delay));
  const content = isConnectionTest ? 'PRISM_OK' : JSON.stringify(aiGuide, null, 2);
  const response = {
    id: 'chatcmpl-prism-mock',
    object: 'chat.completion',
    model: parsed.model || 'mock-study',
    choices: [{
      index: 0,
      message: { role: 'assistant', content },
      finish_reason: 'stop'
    }],
    usage: { prompt_tokens: body.length / 4, completion_tokens: content.length / 4 }
  };
  const payload = JSON.stringify(response);
  res.writeHead(200, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(payload)
  });
  res.end(payload);
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[mock-ai] OpenAI-compatible mock listening on http://127.0.0.1:${PORT}/v1`);
});
