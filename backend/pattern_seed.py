"""Curated pattern curriculum — data, not logic (see patterns.py for that).

Two halves, and they come from different places:

* The DSA half is a transcription of Prerak's own "DSA patterns" sheet: the
  same sixteen patterns, in the sheet's order, with the sheet's problems and
  its sub-groupings ("Kth", "Traversal", "2 heaps"). Where one row bundled
  several LeetCode links — three "remove duplicates" variants, four stock
  problems — they are split into separate entries, because counting four
  problems as one would make every coverage number a lie.
* The system design half has no equivalent sheet, so it is a starting set: the
  techniques an LLD/HLD round actually probes, with the standard prompts that
  exercise each. Prune it to taste; nothing here is load-bearing.

`idea` is the field that earns this file its place. It is deliberately not a
template, and not a recognition cue ("if you see a sorted array, reach for
X") — it states the invariant that makes the technique correct, because that
is what survives contact with a problem you have not seen before. Hold new
entries to that standard.

Seeding is idempotent (`patterns.seed`), so this list can grow: re-seeding adds
what is new and never touches a confidence, note or revisit already recorded.
"""

from __future__ import annotations

from typing import Any

PATTERNS: list[dict[str, Any]] = [
    {
        "key": "two_pointers",
        "name": "Two Pointers",
        "domain": "dsa",
        "order": 1,
        "idea": (
            "Two indices walking the same sequence under a rule that lets each step "
            "rule out a candidate for good. On sorted input the rule is one comparison, "
            "and that permanence is the whole saving: what a quadratic search would "
            "revisit, this discards. State what the span between the pointers still "
            "guarantees and the bound falls out."
        ),
        "problems": [
            {
                "title": "Pair with Target Sum",
                "url": "https://leetcode.com/problems/two-sum-ii-input-array-is-sorted/description/",
                "difficulty": "easy",
            },
            {
                "title": "Rearrange 0 and 1",
                "url": "https://www.geeksforgeeks.org/problems/segregate-0s-and-1s5106/1",
            },
            {
                "title": "Remove Duplicates",
                "url": "https://leetcode.com/problems/remove-duplicates-from-sorted-list/",
                "difficulty": "easy",
            },
            {
                "title": "Remove Duplicates from Sorted Array",
                "url": "https://leetcode.com/problems/remove-duplicates-from-sorted-array/description/",
                "difficulty": "easy",
            },
            {
                "title": "Remove Duplicates from Sorted Array II",
                "url": "https://leetcode.com/problems/remove-duplicates-from-sorted-array-ii/",
                "difficulty": "easy",
            },
            {
                "title": "Squaring a Sorted Array",
                "url": "https://leetcode.com/problems/squares-of-a-sorted-array/",
                "difficulty": "easy",
            },
            {
                "title": "Triplet Sum to Zero",
                "url": "https://leetcode.com/problems/3sum/",
                "difficulty": "medium",
            },
            {
                "title": "Triplet Sum Close to Target",
                "url": "https://leetcode.com/problems/3sum-closest/",
                "difficulty": "medium",
            },
            {
                "title": "Triplets with Smaller Sum",
                "url": "https://www.geeksforgeeks.org/problems/count-triplets-with-sum-smaller-than-x5549/1",
                "difficulty": "medium",
            },
            {
                "title": "Subarrays with Product Less than a Target",
                "url": "https://leetcode.com/problems/subarray-product-less-than-k/",
                "difficulty": "medium",
            },
            {
                "title": "Dutch National Flag Problem",
                "url": "https://leetcode.com/problems/sort-colors/description/",
                "difficulty": "medium",
            },
            {
                "title": "Quadruple Sum to Target",
                "url": "https://leetcode.com/problems/4sum/",
                "difficulty": "medium",
                "challenge": True,
            },
            {
                "title": "Comparing Strings containing Backspaces",
                "url": "https://leetcode.com/problems/backspace-string-compare/",
                "difficulty": "medium",
                "challenge": True,
            },
            {
                "title": "Minimum Window Sort",
                "url": "https://leetcode.com/problems/shortest-unsorted-continuous-subarray/",
                "difficulty": "medium",
                "challenge": True,
                "refs": ["https://www.ideserve.co.in/learn/minimum-length-subarray-sorting-which-results-in-sorted-array"],
            },
        ],
    },
    {
        "key": "fast_slow_pointers",
        "name": "Fast & Slow Pointers",
        "domain": "dsa",
        "order": 2,
        "idea": (
            "Two walkers over the same sequence at different speeds. Their gap changes "
            "by a fixed amount every step, so whether they ever meet is arithmetic "
            "rather than search — and where they meet locates structure (a cycle's "
            "entry, the midpoint) without knowing the length up front."
        ),
        "problems": [
            {
                "title": "LinkedList Cycle",
                "url": "https://leetcode.com/problems/linked-list-cycle/",
                "difficulty": "easy",
            },
            {
                "title": "Start of LinkedList Cycle",
                "url": "https://leetcode.com/problems/linked-list-cycle-ii/",
                "difficulty": "medium",
            },
            {
                "title": "Happy Number",
                "url": "https://leetcode.com/problems/happy-number/",
                "difficulty": "medium",
            },
            {
                "title": "FIND DUPLICATE NUMBER",
                "url": "https://leetcode.com/problems/find-the-duplicate-number/description/",
            },
            {
                "title": "Middle of the LinkedList",
                "url": "https://leetcode.com/problems/middle-of-the-linked-list/",
                "difficulty": "easy",
            },
            {
                "title": "Palindrome LinkedList",
                "url": "https://leetcode.com/problems/palindrome-linked-list/",
                "difficulty": "medium",
                "challenge": True,
            },
            {
                "title": "Rearrange a LinkedList",
                "url": "https://leetcode.com/problems/reorder-list/",
                "difficulty": "medium",
                "challenge": True,
            },
            {
                "title": "Cycle in a Circular Array",
                "url": "https://leetcode.com/problems/circular-array-loop/",
                "difficulty": "hard",
                "challenge": True,
            },
        ],
    },
    {
        "key": "sliding_window",
        "name": "Sliding Window",
        "domain": "dsa",
        "order": 3,
        "idea": (
            "A contiguous range whose ends only ever move forward, so no element is "
            "examined twice. It is correct only when the property is monotone in the "
            "window: growing can break it, shrinking can only repair it. If that does "
            "not hold, the window is the wrong tool however tempting the shape."
        ),
        "problems": [
            {
                "title": "Maximum Sum Subarray of Size K",
                "url": "https://www.geeksforgeeks.org/problems/max-sum-subarray-of-size-k5313/1",
                "difficulty": "easy",
            },
            {
                "title": "Smallest Subarray with a given sum",
                "url": "https://leetcode.com/problems/minimum-size-subarray-sum/",
                "difficulty": "easy",
            },
            {
                "title": "Longest Substring with K Distinct Characters",
                "url": "https://www.geeksforgeeks.org/problems/longest-k-unique-characters-substring0853/1",
                "difficulty": "medium",
            },
            {
                "title": "Fruits into Baskets",
                "url": "https://leetcode.com/problems/fruit-into-baskets/",
                "difficulty": "medium",
            },
            {
                "title": "No-repeat Substring",
                "url": "https://leetcode.com/problems/longest-substring-without-repeating-characters/",
                "difficulty": "hard",
            },
            {
                "title": "Longest Substring with Same Letters after Replacement",
                "url": "https://leetcode.com/problems/longest-repeating-character-replacement/",
                "difficulty": "hard",
            },
            {
                "title": "Longest Subarray with Ones after Replacement",
                "url": "https://leetcode.com/problems/max-consecutive-ones-iii/",
                "difficulty": "hard",
            },
            {
                "title": "Minimum size subarray SUM",
                "url": "https://leetcode.com/problems/minimum-size-subarray-sum/",
            },
            {
                "title": "MInimum Size Substring",
                "url": "https://leetcode.com/problems/minimum-window-substring/description/?envType=study-plan-v2&envId=top-interview-150",
                "difficulty": "hard",
            },
            {
                "title": "Permutation in a String",
                "url": "https://leetcode.com/problems/permutation-in-string/",
                "difficulty": "hard",
                "challenge": True,
            },
            {
                "title": "String Anagrams",
                "url": "https://leetcode.com/problems/find-all-anagrams-in-a-string/",
                "difficulty": "hard",
                "challenge": True,
            },
            {
                "title": "Words Concatenation",
                "url": "https://leetcode.com/problems/substring-with-concatenation-of-all-words/",
                "difficulty": "hard",
                "challenge": True,
            },
        ],
    },
    {
        "key": "kadane",
        "name": "Kadane",
        "domain": "dsa",
        "order": 4,
        "idea": (
            "Ask at every index what the best answer *ending here* is. That one number "
            "depends only on the previous one, so a single scan carries the entire "
            "history. The whole difficulty is picking the quantity that is actually "
            "recursive — best-ending-here, not best-seen-so-far."
        ),
        "problems": [
            {
                "title": "Maximum subarray sum",
                "url": "https://leetcode.com/problems/maximum-subarray/?utm_source=chatgpt.com",
            },
            {
                "title": "Minimum Subarray Sum",
                "url": "https://www.geeksforgeeks.org/problems/smallest-sum-contiguous-subarray/1",
            },
            {
                "title": "Maximum product subarray",
                "url": "https://leetcode.com/problems/maximum-product-subarray/?utm_source=chatgpt.com",
            },
            {
                "title": "Maximum subarray sum with one deletion",
                "url": "https://leetcode.com/problems/maximum-subarray-sum-with-one-deletion/description/",
            },
            {
                "title": "Maximum absolute sum of any subarray",
                "url": "https://leetcode.com/problems/maximum-absolute-sum-of-any-subarray/",
            },
            {
                "title": "Maximum sum in circular array variant",
                "url": "https://leetcode.com/problems/maximum-sum-circular-subarray/?utm_source=chatgpt.com",
            },
        ],
    },
    {
        "key": "prefix_sum",
        "name": "Prefix Sum",
        "domain": "dsa",
        "order": 5,
        "idea": (
            "Precompute running totals so any range reduces to a difference of two of "
            "them. Paired with a hash map it turns \"count the ranges with property P\" "
            "into \"count the earlier prefixes satisfying an equation\", which is the "
            "step that makes the hard variants tractable."
        ),
        "problems": [
            {
                "title": "Subarray Sum Equals K",
                "url": "https://leetcode.com/problems/subarray-sum-equals-k/description/",
                "difficulty": "easy",
            },
            {
                "title": "Find Pivot Index",
                "url": "https://leetcode.com/problems/find-pivot-index/description/",
                "difficulty": "easy",
            },
            {
                "title": "Subarray Sums Divisible By K",
                "url": "https://leetcode.com/problems/subarray-sums-divisible-by-k/description/",
                "difficulty": "medium",
            },
            {
                "title": "Contiguous array",
                "url": "https://leetcode.com/problems/contiguous-array/description/",
                "difficulty": "medium",
            },
            {
                "title": "Shortest Subarray With Sum at Least K",
                "url": "https://leetcode.com/problems/shortest-subarray-with-sum-at-least-k/description/",
                "difficulty": "hard",
                "challenge": True,
            },
            {
                "title": "Count Range Sum",
                "url": "https://leetcode.com/problems/count-of-range-sum/description/",
                "difficulty": "hard",
                "challenge": True,
            },
        ],
    },
    {
        "key": "merge_intervals",
        "name": "Merge Intervals",
        "domain": "dsa",
        "order": 6,
        "idea": (
            "Sort by start and the only interval that can overlap the one you are "
            "building is the next one. Sorting is what collapses a pairwise comparison "
            "into a single pass; the invariant is that everything already emitted is "
            "final."
        ),
        "problems": [
            {
                "title": "Merge Intervals",
                "url": "https://leetcode.com/problems/merge-intervals/description/",
                "difficulty": "medium",
            },
            {
                "title": "Insert Interval",
                "url": "https://leetcode.com/problems/insert-interval/",
                "difficulty": "medium",
            },
            {
                "title": "Intervals Intersection",
                "url": "https://leetcode.com/problems/interval-list-intersections/description/",
                "difficulty": "medium",
            },
            {
                "title": "Overlapping Intervals",
                "url": "https://www.geeksforgeeks.org/check-if-any-two-intervals-overlap-among-a-given-set-of-intervals/",
                "refs": ["https://www.geeksforgeeks.org/check-if-any-two-intervals-overlap-among-a-given-set-of-intervals/"],
            },
            {
                "title": "Minimum Meeting Rooms",
                "url": "https://www.geeksforgeeks.org/problems/attend-all-meetings-ii/1",
                "difficulty": "hard",
                "challenge": True,
            },
            {
                "title": "Maximum CPU Load",
                "url": "https://www.geeksforgeeks.org/maximum-cpu-load-from-the-given-list-of-jobs/",
                "difficulty": "hard",
                "challenge": True,
                "refs": ["https://www.geeksforgeeks.org/maximum-cpu-load-from-the-given-list-of-jobs/"],
            },
            {
                "title": "Employee Free Time",
                "url": "https://www.codertrain.co/employee-free-time",
                "difficulty": "hard",
                "challenge": True,
                "refs": ["https://www.codertrain.co/employee-free-time"],
            },
        ],
    },
    {
        "key": "linked_list_reversal",
        "name": "In-place Reversal of a Linked List",
        "domain": "dsa",
        "order": 7,
        "idea": (
            "Re-aim one link per step while holding previous, current and next. Sub- "
            "list variants differ only in where the reversed run is spliced back in, so "
            "name the four boundary nodes before writing a line — that is where these "
            "go wrong, not in the loop."
        ),
        "problems": [
            {
                "title": "Reverse a LinkedList",
                "url": "https://leetcode.com/problems/reverse-linked-list/",
                "difficulty": "easy",
            },
            {
                "title": "Reverse a Sub-list",
                "url": "https://leetcode.com/problems/reverse-linked-list-ii/",
                "difficulty": "medium",
            },
            {
                "title": "Reverse List in Pairs",
                "url": "https://leetcode.com/problems/swap-nodes-in-pairs/description/",
                "difficulty": "medium",
            },
            {
                "title": "Reverse every K-element Sub-list",
                "url": "https://leetcode.com/problems/reverse-nodes-in-k-group/",
                "difficulty": "hard",
            },
            {
                "title": "Reverse nodes in EVEN Length Groups",
                "url": "https://leetcode.com/problems/reverse-nodes-in-even-length-groups/description/",
                "difficulty": "hard",
                "challenge": True,
            },
            {
                "title": "Rotate a LinkedList",
                "url": "https://leetcode.com/problems/rotate-list/",
                "difficulty": "medium",
                "challenge": True,
            },
        ],
    },
    {
        "key": "monotonic_stack",
        "name": "Stack & Monotonic Stack",
        "domain": "dsa",
        "order": 8,
        "idea": (
            "A stack kept in order because anything violating the order is popped on "
            "arrival. Every element is pushed and popped at most once, so \"the next "
            "thing bigger than this\" costs linear time. The element you pop *at* is the "
            "answer to the popped one's question."
        ),
        "problems": [
            {
                "title": "remove adjacent duplicates",
                "url": "https://leetcode.com/problems/remove-all-adjacent-duplicates-in-string/description/",
            },
            {
                "title": "Balanced Parentheses",
                "url": "https://leetcode.com/problems/valid-parentheses/description/",
            },
            {"title": "Reverse a String", "url": None},
            {
                "title": "Next Greater Element",
                "url": "https://leetcode.com/problems/next-greater-element-ii/description/",
                "difficulty": "easy",
            },
            {
                "title": "Daily Temperatures",
                "url": "https://leetcode.com/problems/daily-temperatures/",
                "difficulty": "easy",
            },
            {
                "title": "Remove Nodes From Linked List",
                "url": "https://leetcode.com/problems/remove-nodes-from-linked-list/",
                "difficulty": "easy",
            },
            {
                "title": "Remove All Adjacent Duplicates in String II",
                "url": "https://leetcode.com/problems/remove-all-adjacent-duplicates-in-string-ii/",
                "difficulty": "medium",
            },
            {
                "title": "Simplify Path",
                "url": "https://leetcode.com/problems/simplify-path/",
                "challenge": True,
            },
            {
                "title": "Remove K Digits",
                "url": "https://leetcode.com/problems/remove-k-digits/",
                "difficulty": "hard",
                "challenge": True,
            },
        ],
    },
    {
        "key": "hash_maps",
        "name": "Hash Maps",
        "domain": "dsa",
        "order": 9,
        "idea": (
            "Spend space to answer \"have I seen this, and where?\" in constant time. "
            "Most counting and pairing problems are one pass plus the right key — and "
            "choosing the key *is* the problem, not an implementation detail."
        ),
        "problems": [
            {
                "title": "First Non-repeating Character",
                "url": "https://leetcode.com/problems/first-unique-character-in-a-string/",
                "difficulty": "easy",
            },
            {
                "title": "Maximum Number of Balloons",
                "url": "https://leetcode.com/problems/maximum-number-of-balloons/",
                "difficulty": "easy",
            },
            {
                "title": "Longest Palindrome",
                "url": "https://leetcode.com/problems/longest-palindrome/",
                "difficulty": "easy",
            },
            {
                "title": "Ransom Note",
                "url": "https://leetcode.com/problems/ransom-note/",
                "difficulty": "easy",
            },
        ],
    },
    {
        "key": "binary_search",
        "name": "Binary Search",
        "domain": "dsa",
        "order": 10,
        "idea": (
            "Halve a space in which some predicate is false up to a point and true "
            "after it. Sortedness is not the requirement; monotonicity of the predicate "
            "is. Searching on the answer is the same idea with the candidate answer as "
            "the axis rather than an index."
        ),
        "problems": [
            {
                "title": "Binary search basic",
                "url": "https://leetcode.com/problems/binary-search/",
            },
            {
                "title": "Upper Bound/ Ceiling",
                "url": "https://www.geeksforgeeks.org/problems/ceil-in-a-sorted-array/1",
            },
            {
                "title": "First and Last position",
                "url": "https://leetcode.com/problems/find-first-and-last-position-of-element-in-sorted-array/",
            },
            {
                "title": "Count number of occurences",
                "url": "https://www.geeksforgeeks.org/problems/number-of-occurrence2259/1",
            },
            {
                "title": "Search in infinite Sorted array",
                "url": "https://www.geeksforgeeks.org/find-position-element-sorted-array-infinite-numbers/",
                "refs": ["https://www.geeksforgeeks.org/find-position-element-sorted-array-infinite-numbers/"],
            },
            {
                "title": "Peak index in Mountain",
                "url": "https://leetcode.com/problems/peak-index-in-a-mountain-array/",
            },
            {
                "title": "Find peak in mountain range",
                "url": "https://leetcode.com/problems/find-peak-element/",
            },
            {
                "title": "Find minimum in rotated sorted array",
                "url": "https://leetcode.com/problems/find-minimum-in-rotated-sorted-array/",
            },
            {
                "title": "Find number of rotations to sorted array",
                "url": "https://www.geeksforgeeks.org/problems/rotation4723/1",
            },
            {
                "title": "Search in rotated sorted array",
                "url": "https://leetcode.com/problems/search-in-rotated-sorted-array/description/",
            },
            {
                "title": "KOKO eating BANANAS",
                "url": "https://leetcode.com/problems/koko-eating-bananas/",
            },
            {
                "title": "Min num of days to make m bouquets",
                "url": "https://leetcode.com/problems/minimum-number-of-days-to-make-m-bouquets/",
            },
            {
                "title": "Aggresive cows",
                "url": "https://www.geeksforgeeks.org/problems/aggressive-cows/1",
            },
            {
                "title": "H index 2",
                "url": "https://leetcode.com/problems/h-index-ii/description/",
            },
            {
                "title": "Max candies to k children",
                "url": "https://leetcode.com/problems/maximum-candies-allocated-to-k-children/description/",
            },
            {
                "title": "Capacity to ship packages in d days",
                "url": "https://leetcode.com/problems/capacity-to-ship-packages-within-d-days/description/",
            },
            {
                "title": "Book Allocation Problem",
                "url": "https://www.geeksforgeeks.org/problems/allocate-minimum-number-of-pages0937/1",
            },
            {
                "title": "Split largest arrray",
                "url": "https://leetcode.com/problems/split-array-largest-sum/description/",
            },
            {
                "title": "Search 2 D matrix",
                "url": "https://leetcode.com/problems/search-a-2d-matrix/",
            },
            {
                "title": "Search 2D matrix",
                "url": "https://leetcode.com/problems/search-a-2d-matrix-ii/description/",
                "difficulty": "hard",
            },
            {
                "title": "kth smallest in sorted matrix",
                "url": "https://leetcode.com/problems/kth-smallest-element-in-a-sorted-matrix/description/",
            },
            {
                "title": "kth smallest in multiplication matrix",
                "url": "https://leetcode.com/problems/kth-smallest-number-in-multiplication-table/description/",
            },
            {
                "title": "median of 2 sorted arrays",
                "url": "https://leetcode.com/problems/median-of-two-sorted-arrays/",
            },
        ],
    },
    {
        "key": "heaps",
        "name": "Heaps",
        "domain": "dsa",
        "order": 11,
        "idea": (
            "Keep only what could still matter and pay log k to maintain it. A heap "
            "answers \"what is the extreme of the set so far\" under insertion, which is "
            "what makes streaming and k-selection cheap; two heaps facing each other "
            "keep a median in view."
        ),
        "problems": [
            {
                "title": "kth smallest",
                "url": "https://www.geeksforgeeks.org/problems/kth-smallest-element5635/1",
                "group": "Kth",
            },
            {
                "title": "kth largest",
                "url": "https://leetcode.com/problems/kth-largest-element-in-an-array/description/",
                "group": "Kth",
            },
            {
                "title": "TOP K frequent Elements",
                "url": "https://leetcode.com/problems/top-k-frequent-elements/description/",
                "group": "Kth",
            },
            {
                "title": "Top K frequent Words",
                "url": "https://leetcode.com/problems/top-k-frequent-words/description/",
                "group": "Kth",
            },
            {
                "title": "K closest points to origin",
                "url": "https://leetcode.com/problems/k-closest-points-to-origin/description/",
                "group": "K closest",
            },
            {
                "title": "Find K closest elements",
                "url": "https://leetcode.com/problems/find-k-closest-elements/description/",
                "group": "K closest",
            },
            {
                "title": "Kth weakest row in Matrix",
                "url": "https://leetcode.com/problems/the-k-weakest-rows-in-a-matrix/description/",
                "group": "K closest",
            },
            {
                "title": "Merge K Sorted Arrays",
                "url": "https://www.geeksforgeeks.org/problems/merge-k-sorted-arrays/1",
                "group": "heap as pointer",
            },
            {
                "title": "Kth Smallest in Sorted Matrix",
                "url": "https://leetcode.com/problems/kth-smallest-element-in-a-sorted-matrix/description/",
                "group": "heap as pointer",
            },
            {
                "title": "LAST STONE WEIGHT",
                "url": "https://leetcode.com/problems/last-stone-weight/description/",
                "group": "GREEDY+heap",
            },
            {
                "title": "CPU Task Scheduler",
                "url": "https://leetcode.com/problems/task-scheduler/description/",
                "group": "GREEDY+heap",
            },
            {
                "title": "Reorganize String",
                "url": "https://leetcode.com/problems/reorganize-string/",
                "group": "GREEDY+heap",
            },
            {
                "title": "Min number of refueling stops",
                "url": "https://leetcode.com/problems/minimum-number-of-refueling-stops/description/",
                "group": "GREEDY+heap",
            },
            {
                "title": "IPO",
                "url": "https://leetcode.com/problems/ipo/description/",
                "group": "GREEDY+heap",
            },
            {
                "title": "Course Scheduler 3",
                "url": "https://leetcode.com/problems/course-schedule-iii/description/",
                "group": "GREEDY+heap",
            },
            {
                "title": "Find median in data stream",
                "url": "https://leetcode.com/problems/find-median-from-data-stream/description/",
                "group": "2 heaps",
            },
            {
                "title": "Sliding Window Median",
                "url": "https://leetcode.com/problems/sliding-window-median/description/",
                "difficulty": "hard",
                "group": "2 heaps",
            },
        ],
    },
    {
        "key": "backtracking",
        "name": "Recursion & Backtracking",
        "domain": "dsa",
        "order": 12,
        "idea": (
            "Build a partial answer, extend it, then undo the extension exactly. The "
            "undo is the correctness condition: the state you restore has to be "
            "identical to the one you entered with. Pruning is what turns the "
            "enumeration from complete into feasible."
        ),
        "problems": [
            {
                "title": "Fibonnaci",
                "url": "https://leetcode.com/problems/fibonacci-number/description/",
                "refs": ["https://www.youtube.com/watch?v=j4wjZqzhMqc&t"],
            },
            {
                "title": "Check if string is Pallindrome",
                "url": "https://www.geeksforgeeks.org/problems/palindrome-string0817/1",
                "refs": ["https://www.youtube.com/watch?v=j4wjZqzhMqc&t"],
            },
            {
                "title": "Check if Array is Sorted",
                "url": "https://www.geeksforgeeks.org/problems/check-if-an-array-is-sorted0701/1",
                "refs": ["https://www.youtube.com/watch?v=-gC-QEdpvO4"],
            },
            {
                "title": "Sum of digits of a number",
                "url": "https://www.geeksforgeeks.org/problems/sum-of-digits1742/1",
                "refs": ["https://www.youtube.com/watch?v=-gC-QEdpvO4"],
            },
            {
                "title": "Remove occurences of a character in string",
                "url": "https://www.geeksforgeeks.org/problems/remove-all-occurrences-of-a-character-in-a-string/1",
                "refs": ["https://www.youtube.com/watch?v=-gC-QEdpvO4"],
            },
            {
                "title": "Generate parenthesis",
                "url": "https://leetcode.com/problems/generate-parentheses/description/",
            },
            {
                "title": "Letter Combinations of phone number",
                "url": "https://leetcode.com/problems/letter-combinations-of-a-phone-number/description/",
                "refs": ["https://www.youtube.com/watch?v=IKfIT6uFOcs"],
            },
            {
                "title": "Permutations",
                "url": "https://leetcode.com/problems/permutations/description/",
            },
            {
                "title": "Combination Sum",
                "url": "https://leetcode.com/problems/combination-sum/description/",
            },
            {
                "title": "Pallindrome partition",
                "url": "https://leetcode.com/problems/palindrome-partitioning/description/",
            },
        ],
    },
    {
        "key": "trees",
        "name": "Trees",
        "domain": "dsa",
        "order": 13,
        "idea": (
            "Recursion where the shape of the data is the shape of the call stack. Each "
            "call answers one question about its own subtree and returns it; the parent "
            "combines the answers. Most tree bugs are state pushed downward that should "
            "have been returned upward."
        ),
        "problems": [
            {
                "title": "Inorder",
                "url": "https://leetcode.com/problems/binary-tree-inorder-traversal/description/",
                "group": "Traversal",
            },
            {
                "title": "Preorder",
                "url": "https://leetcode.com/problems/binary-tree-preorder-traversal/description/",
                "group": "Traversal",
            },
            {
                "title": "Postorder",
                "url": "https://leetcode.com/problems/binary-tree-postorder-traversal/description/",
                "group": "Traversal",
            },
            {
                "title": "Level Order",
                "url": "https://leetcode.com/problems/binary-tree-level-order-traversal/description/",
                "group": "Traversal",
            },
            {
                "title": "ZigZag Order",
                "url": "https://leetcode.com/problems/binary-tree-zigzag-level-order-traversal/description/",
                "group": "Traversal",
            },
            {
                "title": "Level Order II",
                "url": "https://leetcode.com/problems/binary-tree-level-order-traversal-ii/description/",
                "group": "Traversal",
            },
            {
                "title": "Invert Tree",
                "url": "https://leetcode.com/problems/invert-binary-tree/description/",
                "group": "Mirror and Symmetry",
            },
            {
                "title": "Symmetric Tree",
                "url": "https://leetcode.com/problems/symmetric-tree/description/",
                "group": "Mirror and Symmetry",
            },
            {
                "title": "Same Tree",
                "url": "https://leetcode.com/problems/same-tree/description/",
                "group": "Mirror and Symmetry",
            },
            {
                "title": "Subtree of another TREE",
                "url": "https://leetcode.com/problems/subtree-of-another-tree/description/",
                "group": "Mirror and Symmetry",
            },
            {
                "title": "Flip Equivalent Tree",
                "url": "https://leetcode.com/problems/flip-equivalent-binary-trees/description/",
                "group": "Mirror and Symmetry",
            },
            {
                "title": "LCA of Binary TREE",
                "url": "https://leetcode.com/problems/lowest-common-ancestor-of-a-binary-tree/description/",
                "group": "Search",
            },
            {
                "title": "Binary Search Tree",
                "url": "https://leetcode.com/problems/search-in-a-binary-search-tree/",
                "group": "Search",
            },
            {
                "title": "LCA of BST",
                "url": "https://leetcode.com/problems/lowest-common-ancestor-of-a-binary-search-tree/description/",
                "group": "Search",
            },
            {
                "title": "LCA of Deepest Leaves",
                "url": "https://leetcode.com/problems/lowest-common-ancestor-of-deepest-leaves/description/",
                "group": "Search",
            },
            {
                "title": "Two Sum IV",
                "url": "https://leetcode.com/problems/two-sum-iv-input-is-a-bst/description/",
                "group": "Search",
            },
            {
                "title": "Kth smallest element in BST",
                "url": "https://leetcode.com/problems/kth-smallest-element-in-a-bst/description/",
                "group": "Search",
            },
            {
                "title": "Minimum Depth of Binary Tree",
                "url": "https://leetcode.com/problems/minimum-depth-of-binary-tree/description/",
                "group": "Validation",
            },
            {
                "title": "Maximum Depth of Binary Tree",
                "url": "https://leetcode.com/problems/maximum-depth-of-binary-tree/description/",
                "group": "Validation",
            },
            {
                "title": "Balanced Binary Tree",
                "url": "https://leetcode.com/problems/balanced-binary-tree/description/",
                "group": "Validation",
            },
            {
                "title": "Diameter of Binary Tree",
                "url": "https://leetcode.com/problems/diameter-of-binary-tree/description/",
                "group": "Validation",
            },
            {
                "title": "Check Completeness of Binary Tree",
                "url": "https://leetcode.com/problems/check-completeness-of-a-binary-tree/description/",
                "group": "Validation",
            },
            {
                "title": "Validate BST",
                "url": "https://leetcode.com/problems/validate-binary-search-tree/description/",
                "group": "Validation",
            },
            {
                "title": "Recover BST",
                "url": "https://leetcode.com/problems/recover-binary-search-tree/description/",
                "group": "Validation",
            },
            {
                "title": "Path Sum",
                "url": "https://leetcode.com/problems/path-sum/description/",
                "group": "Path SUM",
            },
            {
                "title": "Path Sum II",
                "url": "https://leetcode.com/problems/path-sum-ii/",
                "group": "Path SUM",
            },
            {
                "title": "Sum of Root to Leaf",
                "url": "https://leetcode.com/problems/sum-root-to-leaf-numbers/description/",
                "group": "Path SUM",
            },
            {
                "title": "Maximum Path Sum",
                "url": "https://leetcode.com/problems/binary-tree-maximum-path-sum/description/",
                "group": "Path SUM",
            },
            {
                "title": "Contruct tree from preorder and inorder",
                "url": "https://leetcode.com/problems/construct-binary-tree-from-preorder-and-inorder-traversal/description/",
                "group": "Construction",
            },
            {
                "title": "Contruct tree from postorder and inorder",
                "url": "https://leetcode.com/problems/construct-binary-tree-from-inorder-and-postorder-traversal/description/",
                "group": "Construction",
            },
            {
                "title": "Sorted Array to BST",
                "url": "https://leetcode.com/problems/convert-sorted-array-to-binary-search-tree/description/",
                "group": "Construction",
            },
        ],
    },
    {
        "key": "graphs",
        "name": "Graphs",
        "domain": "dsa",
        "order": 14,
        "idea": (
            "A traversal plus a record of what is already settled. The visited set is "
            "not an optimisation — it is what makes termination and correctness hold "
            "once cycles are possible. The order you take vertices in decides what the "
            "traversal actually computes, and weights change which orders are "
            "admissible."
        ),
        "problems": [
            {
                "title": "Construct Adjancency List from EDGES+Nodes",
                "url": "https://www.geeksforgeeks.org/problems/print-adjacency-list-1587115620/1",
            },
            {
                "title": "Graph DFS",
                "url": "https://www.geeksforgeeks.org/problems/depth-first-traversal-for-a-graph/1",
            },
            {
                "title": "GRAPH BFS",
                "url": "https://www.geeksforgeeks.org/problems/bfs-traversal-of-graph/1",
            },
            {
                "title": "Number of Islands",
                "url": "https://leetcode.com/problems/number-of-islands/description/",
            },
            {
                "title": "Number of Provinces",
                "url": "https://leetcode.com/problems/number-of-provinces/description/",
            },
            {
                "title": "Rotten Oranges",
                "url": "https://leetcode.com/problems/rotting-oranges/",
            },
            {
                "title": "Cycle detection in undirected graph",
                "url": "https://www.geeksforgeeks.org/problems/detect-cycle-in-an-undirected-graph/1",
            },
            {
                "title": "Cycle detection in directed graph",
                "url": "https://www.geeksforgeeks.org/problems/detect-cycle-in-a-directed-graph/1",
            },
            {
                "title": "Topological sort",
                "url": "https://www.geeksforgeeks.org/problems/topological-sort/1",
            },
            {
                "title": "Bipartite Graph/ Graph Coloring",
                "url": "https://leetcode.com/problems/is-graph-bipartite/",
            },
            {
                "title": "Surrounded Regoins",
                "url": "https://leetcode.com/problems/surrounded-regions/",
            },
            {
                "title": "Shortest Path in Non-Weighted Graph",
                "url": "https://www.geeksforgeeks.org/problems/shortest-path-in-undirected-graph-having-unit-distance/1",
            },
            {
                "title": "Dijkstra's Algorithm",
                "url": "https://www.geeksforgeeks.org/problems/implementing-dijkstra-set-1-adjacency-matrix/1",
            },
            {
                "title": "Network Delay",
                "url": "https://leetcode.com/problems/network-delay-time/",
            },
            {
                "title": "Path With Minimum Effort",
                "url": "https://leetcode.com/problems/path-with-minimum-effort/",
            },
            {
                "title": "Swim in Rising Water",
                "url": "https://leetcode.com/problems/swim-in-rising-water/",
            },
            {
                "title": "Bellman ford",
                "url": "https://www.geeksforgeeks.org/problems/distance-from-the-source-bellman-ford-algorithm/1",
            },
            {
                "title": "Cheapest Path in K stops",
                "url": "https://leetcode.com/problems/cheapest-flights-within-k-stops/description/",
            },
            {
                "title": "Prim MST",
                "url": "https://www.geeksforgeeks.org/problems/minimum-spanning-tree/1",
            },
            {"title": "Word Ladder", "url": "https://leetcode.com/problems/word-ladder/"},
        ],
    },
    {
        "key": "dynamic_programming",
        "name": "Dynamic Programming",
        "domain": "dsa",
        "order": 15,
        "idea": (
            "A recurrence over states that many paths reach, so each is worth computing "
            "once. Define the state and say out loud what it means before writing "
            "anything; memoisation and tabulation are then the same recurrence "
            "evaluated from opposite ends."
        ),
        "problems": [
            {
                "title": "Fibonacci",
                "url": "https://leetcode.com/problems/fibonacci-number/description/",
            },
            {
                "title": "Climbing Stairs",
                "url": "https://leetcode.com/problems/climbing-stairs/description/",
            },
            {"title": "House Robber", "url": "https://leetcode.com/problems/house-robber/"},
            {
                "title": "0/1 Knapsack",
                "url": "https://www.geeksforgeeks.org/problems/0-1-knapsack-problem0945/1",
            },
            {"title": "tabulation Intro", "url": None},
            {
                "title": "0/1 Knapsack Tabulation",
                "url": "https://www.geeksforgeeks.org/problems/0-1-knapsack-problem0945/1",
            },
            {
                "title": "Subset sum",
                "url": "https://www.geeksforgeeks.org/problems/subset-sum-problem-1611555638/1",
            },
            {
                "title": "Target Sum",
                "url": "https://www.geeksforgeeks.org/problems/target-sum-1626326450/1",
            },
            {
                "title": "LIS",
                "url": "https://leetcode.com/problems/longest-increasing-subsequence/",
            },
            {"title": "LIS Tabulation", "url": None},
            {
                "title": "LCS",
                "url": "https://leetcode.com/problems/longest-common-subsequence/description/",
            },
            {
                "title": "Unique Paths",
                "url": "https://leetcode.com/problems/unique-paths/description/",
            },
            {
                "title": "Buy Sell Stocks",
                "url": "https://leetcode.com/problems/best-time-to-buy-and-sell-stock/description/",
            },
            {
                "title": "Best Time to Buy and Sell Stock II",
                "url": "https://leetcode.com/problems/best-time-to-buy-and-sell-stock-ii/description/",
            },
            {
                "title": "Best Time to Buy and Sell Stock III",
                "url": "https://leetcode.com/problems/best-time-to-buy-and-sell-stock-iii/description/",
            },
            {
                "title": "Best Time to Buy and Sell Stock IV",
                "url": "https://leetcode.com/problems/best-time-to-buy-and-sell-stock-iv/description/",
            },
            {
                "title": "MIn cost to cut stick",
                "url": "https://leetcode.com/problems/minimum-cost-to-cut-a-stick/",
            },
            {"title": "Revision", "url": None},
        ],
    },
    {
        "key": "greedy",
        "name": "Greedy",
        "domain": "dsa",
        "order": 16,
        "idea": (
            "Commit to the locally best choice and never revisit it. That is valid only "
            "with an exchange argument — any optimal solution can be rewritten to start "
            "with your choice without getting worse. Without the argument it is a guess "
            "that happens to pass the samples."
        ),
        "problems": [
            {"title": "Lemonade", "url": "https://leetcode.com/problems/lemonade-change/"},
            {
                "title": "Jump Game",
                "url": "https://leetcode.com/problems/jump-game/description/",
            },
            {
                "title": "Assign cookies",
                "url": "https://leetcode.com/problems/assign-cookies/description/",
            },
            {
                "title": "Fractional Knapsack",
                "url": "https://www.geeksforgeeks.org/problems/fractional-knapsack-1587115620/1",
            },
        ],
    },
    # ---------------------------------------------------------------- LLD
    {
        "key": "lld_creational",
        "name": "Creational — hiding construction",
        "domain": "lld",
        "order": 17,
        "idea": (
            "Separate deciding *which* object to build from the code that uses it. "
            "The test is mechanical: if adding a new variant forces an edit to any "
            "caller, construction has leaked. Factory, builder and singleton are "
            "three answers to that one question — and the last is a global by "
            "another name, so justify it or avoid it."
        ),
        "problems": [
            {"title": "Design a parking lot", "url": None},
            {"title": "Design a logging framework", "url": None},
            {"title": "Design a notification service", "url": None},
            {"title": "Design a pizza ordering system", "url": None},
        ],
    },
    {
        "key": "lld_behavioural",
        "name": "Behavioural — varying how, not what",
        "domain": "lld",
        "order": 18,
        "idea": (
            "Behaviour that varies goes behind an interface the caller holds, so a "
            "new rule becomes a new class instead of another branch. Strategy swaps "
            "one algorithm, state swaps the whole transition table and can make an "
            "illegal transition unrepresentable, observer inverts who calls whom. "
            "They all treat the same smell: a conditional that grows every time the "
            "requirements do."
        ),
        "problems": [
            {"title": "Design an elevator system", "url": None},
            {"title": "Design a vending machine", "url": None},
            {"title": "Design chess or tic-tac-toe", "url": None},
            {"title": "Design a traffic signal controller", "url": None},
            {"title": "Design a publish-subscribe event bus", "url": None},
        ],
    },
    {
        "key": "lld_structural",
        "name": "Structural — composing objects",
        "domain": "lld",
        "order": 19,
        "idea": (
            "Wrap an object to change what it presents, or to add to it, without "
            "touching it. Composite is the one worth real attention: it lets a tree "
            "of things answer exactly the calls a leaf answers, so the caller stops "
            "having to know which one it is holding."
        ),
        "problems": [
            {"title": "Design an in-memory file system", "url": None},
            {"title": "Design a coffee machine with add-ons", "url": None},
            {"title": "Design an ATM", "url": None},
            {"title": "Design a delivery cart with stacked discounts", "url": None},
        ],
    },
    {
        "key": "lld_concurrency",
        "name": "Concurrency — shared state under threads",
        "domain": "lld",
        "order": 20,
        "idea": (
            "Every invariant that holds in one thread has to be shown to still hold "
            "under interleaving. The design question is what the unit of mutual "
            "exclusion is, and which operations have to be atomic together — not "
            "which lock class to name. A check followed by an act is two operations "
            "unless you made it one."
        ),
        "problems": [
            {"title": "Design a bounded blocking queue", "url": None},
            {"title": "Design a thread-safe LRU cache", "url": None},
            {"title": "Design seat reservation for ticket booking", "url": None},
            {"title": "Design a producer-consumer pipeline", "url": None},
        ],
    },
    # ---------------------------------------------------------------- HLD
    {
        "key": "hld_partitioning",
        "name": "Partitioning & sharding",
        "domain": "hld",
        "order": 21,
        "idea": (
            "Split the data so a request touches one shard, and pick the key from "
            "what the read path asks for rather than from what the write path has "
            "to hand. Consistent hashing exists so that adding a node moves a "
            "fraction of the keys instead of remapping all of them. The bill for a "
            "bad key is the cross-shard query, and no amount of tuning removes it."
        ),
        "problems": [
            {"title": "Design a URL shortener", "url": None},
            {"title": "Design a distributed key-value store", "url": None},
            {"title": "Design a distributed counter", "url": None},
            {"title": "Design Twitter timelines", "url": None},
        ],
    },
    {
        "key": "hld_caching",
        "name": "Caching & invalidation",
        "domain": "hld",
        "order": 22,
        "idea": (
            "A cache is a bet that a read repeats before the data underneath it "
            "changes. Every cache design is really an invalidation design: settle "
            "the staleness you can tolerate first, then pick the write policy that "
            "delivers it. Hit rate is the headline number and the least interesting "
            "one — what happens during a miss storm is what gets asked in the room."
        ),
        "problems": [
            {"title": "Design a news feed", "url": None},
            {"title": "Design a CDN", "url": None},
            {"title": "Design a product catalogue read path", "url": None},
            {"title": "Design an API gateway cache", "url": None},
        ],
    },
    {
        "key": "hld_replication",
        "name": "Replication & consistency",
        "domain": "hld",
        "order": 23,
        "idea": (
            "Copies buy availability and read throughput, and cost you agreement. "
            "Pick the read and write quorum by naming the anomaly you can live "
            "with — a stale read, a lost update, a reordered write. Strong "
            "consistency is a latency and availability bill rather than a free "
            "default, and saying which one you are paying is most of the answer."
        ),
        "problems": [
            {"title": "Design a chat / messaging system", "url": None},
            {"title": "Design a bank ledger", "url": None},
            {"title": "Design a multi-region datastore", "url": None},
            {"title": "Design a real-time leaderboard", "url": None},
        ],
    },
    {
        "key": "hld_queueing",
        "name": "Async work & queues",
        "domain": "hld",
        "order": 24,
        "idea": (
            "A queue converts a latency problem into a backlog problem, which is "
            "only a win when the backlog is observable and the consumer is "
            "idempotent. At-least-once delivery means the consumer owns "
            "deduplication — the broker cannot hand you exactly-once, whatever its "
            "marketing says."
        ),
        "problems": [
            {"title": "Design a notification fan-out system", "url": None},
            {"title": "Design a video transcoding pipeline", "url": None},
            {"title": "Design order processing for checkout", "url": None},
            {"title": "Design a webhook delivery service", "url": None},
        ],
    },
    {
        "key": "hld_rate_limiting",
        "name": "Rate limiting & backpressure",
        "domain": "hld",
        "order": 25,
        "idea": (
            "Decide what to refuse, before the system decides for you by falling "
            "over. Token bucket against leaky bucket against sliding window is "
            "really one question — are bursts allowed — plus a second one: where "
            "the counter lives, because a per-node counter is not the limit you "
            "advertised."
        ),
        "problems": [
            {"title": "Design an API rate limiter", "url": None},
            {"title": "Design a ticket-booking waiting room", "url": None},
            {"title": "Design a crawler's politeness controller", "url": None},
        ],
    },
    {
        "key": "hld_storage",
        "name": "Storage & indexing choices",
        "domain": "hld",
        "order": 26,
        "idea": (
            "The dominant access pattern picks the store, not the other way round. "
            "B-trees favour reads and range scans, LSM trees favour write "
            "throughput and pay for it at compaction time, an inverted index "
            "answers which documents contain a term. Name the query that has to be "
            "fast and the choice defends itself."
        ),
        "problems": [
            {"title": "Design search autocomplete", "url": None},
            {"title": "Design a metrics / time-series store", "url": None},
            {"title": "Design a file storage service", "url": None},
            {"title": "Design a recommendation feature store", "url": None},
        ],
    },
]
