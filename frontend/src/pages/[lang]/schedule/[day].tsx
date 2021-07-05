/** @jsxRuntime classic */
/** @jsx jsx */
import { GetStaticPaths, GetStaticProps } from "next";
import { useRouter } from "next/router";
import React, { Fragment } from "react";
import { DndProvider } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";
import { FormattedMessage } from "react-intl";
import { Box, jsx } from "theme-ui";

import { addApolloState } from "~/apollo/client";
import { formatDay } from "~/components/day-selector/format-day";
import { MetaTags } from "~/components/meta-tags";
import { useLoginState } from "~/components/profile/hooks";
import { ScheduleView } from "~/components/schedule-view";
import { prefetchSharedQueries } from "~/helpers/prefetch";
import { useCurrentUser } from "~/helpers/use-current-user";
import { useCurrentLanguage } from "~/locale/context";
import { Language } from "~/locale/languages";
import {
  querySchedule,
  queryScheduleDays,
  ScheduleQuery,
  useScheduleQuery,
} from "~/types";

const Meta: React.FC<{
  day: string;
  language: Language;
  timezone?: string;
}> = ({ day, language, timezone }) => (
  <FormattedMessage
    id="schedule.pageTitle"
    values={{ day: formatDay(day, language, timezone) }}
  >
    {(text) => <MetaTags title={text} />}
  </FormattedMessage>
);

export const ScheduleDayPage: React.FC = () => {
  const [loggedIn, _] = useLoginState();
  const code = process.env.conferenceCode;

  const router = useRouter();
  const day = router.query.day as string;

  const shouldFetchCurrentUser = loggedIn && router.query.admin !== undefined;
  const { user } = useCurrentUser({ skip: !shouldFetchCurrentUser });
  const shouldShowAdmin = user ? user.canEditSchedule : false;

  const { loading, data } = useScheduleQuery({
    variables: {
      code,
      fetchSubmissions: shouldShowAdmin,
    },
  });

  if (shouldShowAdmin) {
    return (
      <DndProvider backend={HTML5Backend}>
        <PageContent
          loading={loading}
          shouldShowAdmin={shouldShowAdmin}
          data={data}
          day={day}
        />
      </DndProvider>
    );
  }

  return (
    <PageContent
      loading={loading}
      shouldShowAdmin={shouldShowAdmin}
      data={data}
      day={day}
    />
  );
};

type PageContentProps = {
  loading: boolean;
  shouldShowAdmin: boolean;
  data: ScheduleQuery;
  day: string;
};

const PageContent: React.FC<PageContentProps> = ({
  loading,
  shouldShowAdmin,
  data,
  day,
}) => {
  const language = useCurrentLanguage();

  return (
    <React.Fragment>
      <Meta
        day={day}
        language={language}
        timezone={data?.conference.timezone}
      />

      {loading && (
        <Box sx={{ borderTop: "primary" }}>
          <Box
            sx={{ maxWidth: "largeContainer", p: 3, mx: "auto", fontSize: 3 }}
          >
            <FormattedMessage id="schedule.loading" />
          </Box>
        </Box>
      )}
      {!loading && (
        <ScheduleView
          schedule={data}
          day={day}
          shouldShowAdmin={shouldShowAdmin}
        />
      )}
    </React.Fragment>
  );
};

export const getStaticProps: GetStaticProps = async ({ params }) => {
  await Promise.all([
    prefetchSharedQueries(params.lang as string),
    querySchedule({
      code: process.env.conferenceCode,
      fetchSubmissions: false,
    }),
  ]);

  return addApolloState({
    props: {},
    revalidate: 1,
  });
};

export const getStaticPaths: GetStaticPaths = async () => {
  const {
    data: {
      conference: { days },
    },
  } = await queryScheduleDays({
    code: process.env.conferenceCode,
  });

  const paths = [
    ...days.map((day) => ({
      params: {
        lang: "en",
        day: day.day,
      },
    })),
    ...days.map((day) => ({
      params: {
        lang: "it",
        day: day.day,
      },
    })),
  ];

  return {
    paths,
    fallback: false,
  };
};

export default ScheduleDayPage;
