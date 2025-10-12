# Variable Questions Testing Checklist

## Pre-Testing Setup

### Google Sheets Preparation
- [ ] Update "assignments" sheet to include Question1 through Question25 columns
- [ ] Update "student_answers" sheet to include q1_answer through q25_answer columns
- [ ] Update "feedback+grading" sheet to include feedback1/score1 through feedback25/score25 columns
- [ ] Update "feedback_evaluation" sheet accordingly

### Test Assignments Creation
Create the following test assignments in your Google Sheets:

- [ ] **Test_1Q**: Assignment with 1 question (only Question1 filled)
- [ ] **Test_3Q**: Assignment with 3 questions (Question1-3 filled) - backward compatibility test
- [ ] **Test_5Q**: Assignment with 5 questions (Question1-5 filled)
- [ ] **Test_10Q**: Assignment with 10 questions (Question1-10 filled)
- [ ] **Test_25Q**: Assignment with 25 questions (all questions filled)
- [ ] **Test_Sparse**: Assignment with questions at positions 1, 5, 10, 15, 20 (test non-contiguous)

## Core Functionality Tests

### 1. Single Question (1Q)
- [ ] Load assignment successfully
- [ ] See "📝 Round 1 (1 Question)" in header
- [ ] See exactly 1 question rendered
- [ ] Fill in answer and submit
- [ ] Grading completes (should be fast ~3-5 seconds)
- [ ] See feedback card for the 1 question
- [ ] If score >= 8: See success message
- [ ] If score < 8: See warning message "0/1 passed"

### 2. Three Questions (3Q) - Backward Compatibility
- [ ] Load assignment successfully
- [ ] See "📝 Round 1 (3 Questions)" in header
- [ ] See exactly 3 questions rendered
- [ ] Fill in all 3 answers and submit
- [ ] Grading completes in parallel (~5-8 seconds)
- [ ] See 3 feedback cards
- [ ] Completion check works correctly
- [ ] Enhanced feedback works
- [ ] Conversation feature works
- [ ] Retry functionality works with 3 questions

### 3. Five Questions (5Q)
- [ ] Load assignment successfully
- [ ] See "📝 Round 1 (5 Questions)" in header
- [ ] See exactly 5 questions rendered
- [ ] Fill in all 5 answers and submit
- [ ] Grading completes in parallel (~6-9 seconds)
- [ ] See 5 feedback cards with correct scores
- [ ] Completion message shows "X/5 passed"

### 4. Ten Questions (10Q)
- [ ] Load assignment successfully
- [ ] See "📝 Round 1 (10 Questions)" in header
- [ ] All 10 questions render correctly
- [ ] Fill in all 10 answers and submit
- [ ] Grading completes with 10 parallel threads (~8-12 seconds)
- [ ] All 10 feedback cards display correctly
- [ ] Scroll functionality works
- [ ] Completion message shows "X/10 passed"

### 5. Twenty-Five Questions (25Q) - Maximum
- [ ] Load assignment successfully
- [ ] See "📝 Round 1 (25 Questions)" in header
- [ ] All 25 questions render correctly (requires scrolling)
- [ ] Fill in all 25 answers and submit
- [ ] Grading completes (~12-20 seconds with 10 concurrent threads)
- [ ] All 25 feedback cards display
- [ ] UI remains responsive with many questions
- [ ] Completion message shows "X/25 passed"

## Advanced Features Testing

### Session Restoration
Test with 3, 5, and 10 question assignments:
- [ ] Submit answers and refresh page
- [ ] Previous answers load correctly for all questions
- [ ] Previous feedback loads correctly for all questions
- [ ] Can continue conversation after refresh

### Retry Functionality
Test with different question counts:
- [ ] Click "Retry" button
- [ ] Correct number of retry question blocks appear
- [ ] Fill new answers for all questions
- [ ] Click "Resubmit New Answers"
- [ ] New answers replace old ones at the top
- [ ] New feedback displays correctly
- [ ] Conversation resets properly

### Enhanced Feedback
- [ ] Works with 1 question
- [ ] Works with 3 questions
- [ ] Works with 10 questions
- [ ] Enhanced feedback displays for all questions

### Conversation Feature
Test that conversation has access to all question contexts:
- [ ] Ask about specific questions (e.g., "Why did I get a low score on Q5?")
- [ ] AI responds with context from correct question
- [ ] Works with varying question counts

## Performance Benchmarks

### Parallel Grading Times (approximate)
- [ ] 1 question: < 5 seconds
- [ ] 3 questions: 5-8 seconds
- [ ] 5 questions: 6-10 seconds
- [ ] 10 questions: 8-13 seconds
- [ ] 25 questions: 12-20 seconds

### Check Debug Output
Look for these in console:
```
[DEBUG] Loaded N active questions for assignment X
[DEBUG] Grading N questions: [1, 2, 3, ...]
[BENCHMARK] All N API calls submitted at X.XXXs
[BENCHMARK] Total parallel grading time: X.XXXs
[BENCHMARK] Questions completed: N/N
```

## Edge Cases

### Empty Validation
- [ ] Try to submit with one answer empty - should show error
- [ ] Try to submit with all answers empty - should show error
- [ ] Error message should mention "all answers"

### Question Numbering
- [ ] Questions display correct numbers (Q1, Q2, Q3, not always starting at Q1)
- [ ] Feedback cards match question numbers
- [ ] Retry section shows correct question numbers

### Data Persistence
- [ ] Answers save to correct columns in Google Sheets
- [ ] Grading saves to correct score/feedback columns
- [ ] All 25 columns exist (even if empty)

### Memory Management
- [ ] Context cache initializes for all active questions
- [ ] Memory system tracks all active questions
- [ ] No memory leaks with large question counts

## Validation Tests

### UI Validation
- [ ] All questions render without layout issues
- [ ] Feedback cards don't overlap
- [ ] Scroll works smoothly with many questions
- [ ] Buttons remain functional with many questions

### Data Validation
- [ ] Check "student_answers" sheet has correct columns filled
- [ ] Check "feedback+grading" sheet has correct score/feedback columns filled
- [ ] Verify execution_id consistency across sheets
- [ ] Verify timestamp formats are correct

## Regression Tests

### Ensure Old Features Still Work
- [ ] Student ID validation
- [ ] Assignment due date checking
- [ ] Started status tracking
- [ ] Round counter
- [ ] Background writing to sheets
- [ ] Enhanced feedback button
- [ ] Conversation feature
- [ ] Scroll to top functionality

## Browser Compatibility

Test on:
- [ ] Chrome
- [ ] Firefox
- [ ] Safari
- [ ] Edge

## Known Limitations

- Maximum 25 questions per assignment
- Maximum 10 concurrent grading threads (can be adjusted in code)
- 60-second timeout per question grading

## Bug Reporting Template

If you find issues, report with:
```
**Assignment**: Test_5Q (5 questions)
**Issue**: Grading stuck after submitting
**Steps to Reproduce**: 
1. Load assignment Test_5Q
2. Fill in all 5 answers
3. Click Submit
4. Grading spinner doesn't complete

**Expected**: Grading completes in 6-10 seconds
**Actual**: Spinner continues indefinitely

**Console Output**: [Paste any error messages]
**Browser**: Chrome 120
```

## Success Criteria

✅ All tests pass with:
- 1 question assignment
- 3 question assignment (backward compatibility)
- 5 question assignment
- 10 question assignment
- 25 question assignment

✅ No errors in console
✅ All data saves correctly to Google Sheets
✅ Performance meets benchmarks
✅ UI remains responsive with all question counts

