# Database comparison

**The two databases don't hold the same data.** My `books.db` has 10,014 books and my partner's has 10,014. 10,014 books are in both, and 33 of them have at least one different value (58 values in all). 0 books are only in mine and 0 only in my partner's.

## How they were compared

- **Databases:** my `books.db` and my partner's database saved as `partner/books.db`.
- **Table:** `books` only. Both databases name its columns the same way, so each column was compared with the column of the same name.
- **Columns compared (29):** `work_id`, `goodreads_book_id`, `book_id`, `best_book_id`, `isbn`, `isbn13`, `isbn_status`, `isbn13_status`, `isbn_original`, `isbn13_original`, `other_id`, `isbn_row_status`, `average_rating`, `work_ratings_count`, `authors`, `original_publication_year`, `original_title`, `title`, `language_code`, `image_url`, `small_image_url`, `books_count`, `work_text_reviews_count`, `ratings_count`, `ratings_1`, `ratings_2`, `ratings_3`, `ratings_4`, `ratings_5`.
- **Left out:** `book_key` (each database's own ID, Decision 21) and `created_run` (only records which run loaded the book).
- **Pairing books:** rules.md Rule 9 order: `work_id`, then `goodreads_book_id`, `book_id`, and the cleaned ISBN, counting a match only when exactly one book has that value. Pairs found on: `work_id` 10,014.
- **Different value:** the values differ, or are stored as different types (for example the number 5 and the text "5"). A book stored as *(empty)* has no value in that column.

## Differences by column

| Column | Books with a different value |
|---|---:|
| `isbn13_status` | 25 |
| `isbn_row_status` | 25 |
| `original_title` | 5 |
| `other_id` | 3 |

## Books only in mine

None.

## Books only in my partner's

None.

## Books in both with a different value

| Book | Column | My value | Partner's value |
|---|---|---|---|
| A Hidden Fire (Elemental Mysteries, #1) (work_id 17897317) | `isbn13_status` | `"empty"` | `"rejected"` |
| A Hidden Fire (Elemental Mysteries, #1) (work_id 17897317) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Anatomy for the Artist (work_id 317880) | `other_id` | *(empty)* | `"635517080452"` |
| Brothers Majere (Dragonlance: Preludes, #3) (work_id 1107914) | `original_title` | `" "` | *(empty)* |
| Captive in the Dark (The Dark Duet, #1) (work_id 17499464) | `isbn13_status` | `"empty"` | `"rejected"` |
| Captive in the Dark (The Dark Duet, #1) (work_id 17499464) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Charade (Games, #1) (work_id 21751013) | `isbn13_status` | `"empty"` | `"rejected"` |
| Charade (Games, #1) (work_id 21751013) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Clash (Crash, #2) (work_id 21573427) | `isbn13_status` | `"empty"` | `"rejected"` |
| Clash (Crash, #2) (work_id 21573427) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Crash (Crash, #1) (work_id 21450735) | `isbn13_status` | `"empty"` | `"rejected"` |
| Crash (Crash, #1) (work_id 21450735) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Cross My Heart (Cross My Heart, #1) (work_id 15714317) | `isbn13_status` | `"empty"` | `"rejected"` |
| Cross My Heart (Cross My Heart, #1) (work_id 15714317) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Eleanor of Aquitaine: A Life  (work_id 977136) | `original_title` | `" "` | *(empty)* |
| Falling into You (Falling, #1) (work_id 24333050) | `isbn13_status` | `"empty"` | `"rejected"` |
| Falling into You (Falling, #1) (work_id 24333050) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Friend-Zoned (Friend-Zoned, #1) (work_id 24502143) | `isbn13_status` | `"empty"` | `"rejected"` |
| Friend-Zoned (Friend-Zoned, #1) (work_id 24502143) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Hearts in Darkness (Hearts in Darkness, #1) (work_id 16101664) | `isbn13_status` | `"empty"` | `"rejected"` |
| Hearts in Darkness (Hearts in Darkness, #1) (work_id 16101664) | `isbn_row_status` | `"empty"` | `"rejected"` |
| If You Stay (Beautifully Broken, #1) (work_id 23348933) | `isbn13_status` | `"empty"` | `"rejected"` |
| If You Stay (Beautifully Broken, #1) (work_id 23348933) | `isbn_row_status` | `"empty"` | `"rejected"` |
| If You Take a Mouse to School (work_id 976480) | `original_title` | `" "` | *(empty)* |
| Maid for the Billionaire (Legacy Collection, #1) (work_id 16166069) | `isbn13_status` | `"empty"` | `"rejected"` |
| Maid for the Billionaire (Legacy Collection, #1) (work_id 16166069) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Out of the Dark (The Grey Wolves, #4) (work_id 19028216) | `isbn13_status` | `"empty"` | `"rejected"` |
| Out of the Dark (The Grey Wolves, #4) (work_id 19028216) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Play with Me (With Me in Seattle, #3) (work_id 23676586) | `isbn13_status` | `"empty"` | `"rejected"` |
| Play with Me (With Me in Seattle, #3) (work_id 23676586) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Raw (RAW Family, #1) (work_id 26129516) | `isbn13_status` | `"empty"` | `"rejected"` |
| Raw (RAW Family, #1) (work_id 26129516) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Reasonable Doubt: Volume 1 (Reasonable Doubt, #1) (work_id 40094032) | `isbn13_status` | `"empty"` | `"rejected"` |
| Reasonable Doubt: Volume 1 (Reasonable Doubt, #1) (work_id 40094032) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Rock with Me (With Me in Seattle, #4) (work_id 23676597) | `isbn13_status` | `"empty"` | `"rejected"` |
| Rock with Me (With Me in Seattle, #4) (work_id 23676597) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Sailor Moon, #1 (Sailor Moon, #1) (work_id 488611) | `other_id` | *(empty)* | `"645573003012"` |
| Sea of Swords (Forgotten Realms: Paths of Darkness, #4; Legend of Drizzt, #13) (work_id 2221220) | `original_title` | `" "` | *(empty)* |
| Second Chance Boyfriend (One Week Girlfriend, #2) (work_id 23984106) | `isbn13_status` | `"empty"` | `"rejected"` |
| Second Chance Boyfriend (One Week Girlfriend, #2) (work_id 23984106) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Seducing Cinderella (Fighting for Love, #1) (work_id 21464225) | `isbn13_status` | `"empty"` | `"rejected"` |
| Seducing Cinderella (Fighting for Love, #1) (work_id 21464225) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Shadows of the Empire (Star Wars) (work_id 858558) | `original_title` | `" "` | *(empty)* |
| The Finding (Law of the Lycans, #5) (work_id 15353639) | `isbn13_status` | `"empty"` | `"rejected"` |
| The Finding (Law of the Lycans, #5) (work_id 15353639) | `isbn_row_status` | `"empty"` | `"rejected"` |
| The Keeping (Law of the Lycans, #3) (work_id 13667879) | `isbn13_status` | `"empty"` | `"rejected"` |
| The Keeping (Law of the Lycans, #3) (work_id 13667879) | `isbn_row_status` | `"empty"` | `"rejected"` |
| The Practice of the Presence of God (work_id 2133549) | `other_id` | *(empty)* | `"630809681058"` |
| Try Me (One Night with Sole Regret, #1) (work_id 19268425) | `isbn13_status` | `"empty"` | `"rejected"` |
| Try Me (One Night with Sole Regret, #1) (work_id 19268425) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Undeniable (Undeniable, #1) (work_id 21882391) | `isbn13_status` | `"empty"` | `"rejected"` |
| Undeniable (Undeniable, #1) (work_id 21882391) | `isbn_row_status` | `"empty"` | `"rejected"` |
| Wait for You (Wait for You, #1) (work_id 23981243) | `isbn13_status` | `"empty"` | `"rejected"` |
| Wait for You (Wait for You, #1) (work_id 23981243) | `isbn_row_status` | `"empty"` | `"rejected"` |
| تاكسي: حواديت المشاوير (work_id 2516225) | `isbn13_status` | `"empty"` | `"rejected"` |
| تاكسي: حواديت المشاوير (work_id 2516225) | `isbn_row_status` | `"empty"` | `"rejected"` |
| واحة الغروب (work_id 3275385) | `isbn13_status` | `"empty"` | `"rejected"` |
| واحة الغروب (work_id 3275385) | `isbn_row_status` | `"empty"` | `"rejected"` |

## Why our data differs

My partner and I compared our databases separately and got the same result: the same 10,014 books, with 33 books differing in the same 58 values. Our `rules.md` files are identical, so the rule text itself isn't different. The differences come from places where our two `ingest.py` scripts handled something differently. Every cleaned ISBN and every rating count matches.

| Difference | Books | Rule it comes from | What let it through |
|---|---:|---|---|
| Non-ISBN codes with no ISBN-10: my `isbn13_status` and `isbn_row_status` say `empty`, my partner's say `rejected` | 25 | Rule 6, Rule 8 and Decision 12, with examples 19 and 29 | **The rule.** Neither test suite could catch it |
| UPCs written in scientific notation: my partner stored them in `other_id`, mine is empty | 3 | Decisions 10, 11 and 12 | **The rule**, then my code. The tests don't cover this form |
| A title that is a single space: my partner stored it as empty, I kept the space | 5 | Database layout: "Stored as they arrived" | **My partner's code.** The tests don't cover it |

**The 25 status differences.** These are values like Barnes & Noble IDs that get moved to `other_id` when the row has no ISBN-10 to calculate from. The rules never say what status a moved value gets. Rule 6 lists these codes as invalid, which points to `rejected`, and my partner's script used that. But the examples table only says "moved" and names no status, and the value isn't really a failed repair because it was kept in `other_id`, which is how my script ended up with `empty`. Both are reasonable readings. The tests couldn't catch it because they follow the examples table, and the table has no status to check. The fix belongs in the rule: say which status a moved value gets.

**The 3 UPCs.** Books 2894, 3689 and 5268 have UPCs written like `6.45573003012e+11`. Decision 11 explains how to recognize a UPC, but only for values ending in `.0`. Decision 10 only covers 13-digit numbers in scientific notation. So no decision covers a 12-digit number in scientific notation. Decision 12 does say UPCs go in `other_id`, and my partner read that as covering this case. My script rejects scientific notation that isn't 13 digits, so the value never reached the UPC check. All three books have a valid ISBN-10, so the ISBN-13 still came out the same. The tests missed it because example 20, the only UPC example, ends in `.0`.

**The 5 titles.** Books 3014, 6598, 7578, 7864 and 9280 have a single space as their `original_title` in `books.csv`. The rule here is clear: the database layout says these columns are stored as they arrived, and Decision 4 says columns other than the ISBNs aren't validated. My partner's script turns a value that's only spaces into an empty one, which no rule asked for, so this is a mistake in my partner's code and my value is the one that follows the rule. The tests let it through because neither suite loads a title made only of spaces.
